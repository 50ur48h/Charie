"""Document facts: extraction, quotes, entries, conflicts and learned (P08.6)."""

from decimal import Decimal

from sqlalchemy import func, select

from charie.learner.steps import doc_facts
from charie.learner.steps.base import StepContext
from charie.learner.steps.doc_facts import compare_run, run_job
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge.store import approve_entry, get_entry
from charie.shared.knowledge.versions import get_or_create_draft
from charie.shared.search import search as search_mod
from charie.shared.search.embeddings import EmbeddingResult
from charie.shared.tables.knowledge import KbEntry
from charie.shared.tables.sources import DocFact, Document, DocumentSection

S1 = "# Net sales\n\nNet sales means total orders minus refunds. Net sales were $1.2M in 2025.\n"
S2 = "# Refunds\n\nFinal sale items can't be refunded. Use code MEGA0926 at checkout.\n"


class _EmbedStub:
    def embed_texts(self, texts, **kwargs):
        return EmbeddingResult(
            vectors=[[1.0] + [0.0] * 1535 for _ in texts],
            prompt_tokens=len(texts),
            cost_usd=Decimal("0"),
        )


def _add_doc(session, name: str = "guide.md", status: str = "reading") -> int:
    row = Document(file_name=name, file_type="md", size_bytes=10, sha256=name, status=status)
    row.progress = 100
    session.add(row)
    session.flush()
    return row.id


def _add_section(session, doc_id: int, position: int, heading: str, text: str) -> int:
    row = DocumentSection(document_id=doc_id, position=position, heading_path=heading, text_=text)
    session.add(row)
    session.flush()
    return row.id


def _ctx(session, version_id: int) -> tuple[StepContext, list]:
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    return (
        StepContext(
            session=session,
            run_id=1,
            version_id=version_id,
            source=None,
            connector=None,
            strict_mode=False,
            settings={},
            say=say,
        ),
        said,
    )


def _client(monkeypatch, fake: FakeAi) -> FakeAi:
    monkeypatch.setattr(
        doc_facts,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    monkeypatch.setattr(search_mod, "embeddings", _EmbedStub())
    return fake


def _seed_two_sections(session) -> tuple[int, int]:
    doc_id = _add_doc(session)
    version = get_or_create_draft(session, "first_learning")
    _add_section(session, doc_id, 0, "Net sales", S1)
    _add_section(session, doc_id, 1, "Refunds", S2)
    session.commit()
    return doc_id, version.id


def _extract_replies() -> FakeAi:
    return (
        FakeAi()
        .reply(
            "extract_doc_facts",
            {
                "facts": [
                    {
                        "kind": "definition",
                        "topic": "Net sales",
                        "statement": "Net sales means total orders minus refunds.",
                        "quote": "Net sales means total orders minus refunds.",
                        "location": "Net sales",
                    },
                    {
                        "kind": "reported_number",
                        "topic": "Net sales 2025",
                        "statement": "Net sales were $1.2M in 2025.",
                        "quote": "Net sales were $1.2M in 2025.",
                        "location": "Net sales",
                    },
                ]
            },
        )
        .reply(
            "extract_doc_facts",
            {
                "facts": [
                    {
                        "kind": "rule",
                        "topic": "Final sale",
                        "statement": "Final sale items can't be refunded.",
                        "quote": "Final sale items can't be refunded.",
                        "location": "Refunds",
                    },
                    {
                        "kind": "code",
                        "topic": "Checkout code",
                        "statement": "MEGA0926 is the checkout code.",
                        "quote": "Use code MEGA0926",
                        "location": "Refunds",
                    },
                ]
            },
        )
    )


def _run_extract(session, monkeypatch, fake, doc_id, version_id):
    _client(monkeypatch, fake)
    ctx, said = _ctx(session, version_id)
    info = JobInfo(id=1, kind="extract_doc_facts", payload={"document_id": doc_id}, run_id=1)
    run_job(info, ctx)
    session.commit()
    return said


def test_extract_learns_document(db_session, monkeypatch) -> None:
    doc_id, version_id = _seed_two_sections(db_session)
    said = _run_extract(db_session, monkeypatch, _extract_replies(), doc_id, version_id)
    doc = db_session.get(Document, doc_id)
    assert (doc.status, doc.fact_count) == ("learned", 4)
    assert doc.learned_at is not None and doc.error is None
    rows = db_session.scalars(select(DocFact).where(DocFact.document_id == doc_id)).all()
    assert all(fact.status == "ok" for fact in rows)
    assert ("found", "Learned 4 fact(s) from guide.md.") in said
    definition = get_entry(db_session, version_id, f"doc.definition.net_sales.{doc_id}")
    assert definition is not None and definition.confidence == "from_document"
    assert definition.meaning == "Net sales means total orders minus refunds."
    assert definition.sources[0]["quote"] == "Net sales means total orders minus refunds."
    assert definition.sources[0]["document"] == "guide.md"
    assert definition.sources[0]["section_id"] == rows[0].section_id
    assert len(definition.embedding) == 1536  # Entries carry vectors for P08.5 search.
    assert get_entry(db_session, version_id, f"doc.rule.final_sale.{doc_id}") is not None
    assert get_entry(db_session, version_id, f"doc.code.checkout_code.{doc_id}") is not None
    assert get_entry(db_session, version_id, f"doc.reported_number.net_sales_2025.{doc_id}") is None
    numbers = [fact for fact in rows if fact.kind == "reported_number"]
    assert len(numbers) == 1 and numbers[0].topic == "Net sales 2025"  # A claim, not knowledge.


def test_extract_twice_has_no_duplicates(db_session, monkeypatch) -> None:
    doc_id, version_id = _seed_two_sections(db_session)
    _run_extract(db_session, monkeypatch, _extract_replies(), doc_id, version_id)
    before_facts = db_session.scalar(select(func.count()).select_from(DocFact))
    before_entries = db_session.scalar(select(func.count()).select_from(KbEntry))
    _run_extract(db_session, monkeypatch, _extract_replies(), doc_id, version_id)
    assert db_session.scalar(select(func.count()).select_from(DocFact)) == before_facts
    assert db_session.scalar(select(func.count()).select_from(KbEntry)) == before_entries


def test_fake_quote_is_dropped(db_session, monkeypatch) -> None:
    doc_id, version_id = _seed_two_sections(db_session)
    fake = (
        FakeAi()
        .reply(
            "extract_doc_facts",
            {
                "facts": [
                    {
                        "kind": "definition",
                        "topic": "Net sales",
                        "statement": "Net sales means everything.",
                        "quote": "Net sales means everything.",
                        "location": "Net sales",
                    }
                ]
            },
        )
        .reply("extract_doc_facts", {"facts": []})
    )
    said = _run_extract(db_session, monkeypatch, fake, doc_id, version_id)
    rows = db_session.scalars(select(DocFact).where(DocFact.document_id == doc_id)).all()
    assert rows == []
    assert any(kind == "warning" and "quotes" in message for kind, message in said)
    assert get_entry(db_session, version_id, f"doc.definition.net_sales.{doc_id}") is None


def test_formula_and_codes(db_session, monkeypatch) -> None:
    doc_id = _add_doc(db_session)
    version = get_or_create_draft(db_session, "first_learning")
    _add_section(
        db_session,
        doc_id,
        0,
        "Prices",
        "# Prices\n\nNet sales equals total orders minus refunds. Use code MEGA0926.\n",
    )
    db_session.commit()
    fake = FakeAi().reply(
        "extract_doc_facts",
        {
            "facts": [
                {
                    "kind": "formula",
                    "topic": "Net sales",
                    "statement": "Net sales equals total orders minus refunds.",
                    "quote": "Net sales equals total orders minus refunds.",
                    "location": "Prices",
                },
                {
                    "kind": "code",
                    "topic": "Checkout code",
                    "statement": "MEGA0926 is the checkout code.",
                    "quote": "Use code MEGA0926.",
                    "location": "Prices",
                },
            ]
        },
    )
    _run_extract(db_session, monkeypatch, fake, doc_id, version.id)
    assert get_entry(db_session, version.id, f"doc.formula.net_sales.{doc_id}") is None
    assert get_entry(db_session, version.id, f"doc.code.checkout_code.{doc_id}") is not None


def test_compare_conflict(db_session, monkeypatch) -> None:
    doc_id, version_id = _seed_two_sections(db_session)
    _run_extract(db_session, monkeypatch, _extract_replies(), doc_id, version_id)
    other = _add_doc(db_session, name="other.md")
    _add_section(
        db_session, other, 0, "Net sales", "# Net sales\n\nNet sales means gross profit.\n"
    )
    db_session.commit()
    fake = FakeAi().reply(
        "extract_doc_facts",
        {
            "facts": [
                {
                    "kind": "definition",
                    "topic": "Net sales",
                    "statement": "Net sales means gross profit.",
                    "quote": "Net sales means gross profit.",
                    "location": "Net sales",
                }
            ]
        },
    )
    _run_extract(db_session, monkeypatch, fake, other, version_id)
    _client(monkeypatch, FakeAi().reply("compare_facts", {"agree": False, "topic": "Net sales"}))
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    conflicts = compare_run(db_session, version_id, [doc_id, other], say=say)
    db_session.commit()
    assert conflicts == ["Net sales"]
    both = db_session.scalars(
        select(DocFact).where(DocFact.topic == "Net sales", DocFact.kind == "definition")
    ).all()
    assert len(both) == 2 and all(fact.status == "conflicting" for fact in both)
    for doc in (doc_id, other):
        entry = get_entry(db_session, version_id, f"doc.definition.net_sales.{doc}")
        assert entry is not None and entry.confidence == "conflicting"
    assert any(kind == "warning" and "Conflict in Net sales" in message for kind, message in said)


def test_compare_agreement_needs_no_ai(db_session, monkeypatch) -> None:
    doc_id, version_id = _seed_two_sections(db_session)
    _run_extract(db_session, monkeypatch, _extract_replies(), doc_id, version_id)
    fake = _client(monkeypatch, FakeAi())
    conflicts = compare_run(db_session, version_id, [doc_id], say=lambda *a, **k: None)
    assert conflicts == []
    assert [call[0] for call in fake.calls] == []


def test_confirmed_entry_untouched(db_session, monkeypatch) -> None:
    doc_id, version_id = _seed_two_sections(db_session)
    _run_extract(db_session, monkeypatch, _extract_replies(), doc_id, version_id)
    key = f"doc.definition.net_sales.{doc_id}"
    entry = get_entry(db_session, version_id, key)
    assert entry is not None
    assert approve_entry(db_session, version_id, key) is True
    db_session.commit()
    other = _add_doc(db_session, name="other.md")
    _add_section(
        db_session, other, 0, "Net sales", "# Net sales\n\nNet sales means gross profit.\n"
    )
    db_session.commit()
    _run_extract(
        db_session,
        monkeypatch,
        FakeAi().reply(
            "extract_doc_facts",
            {
                "facts": [
                    {
                        "kind": "definition",
                        "topic": "Net sales",
                        "statement": "Net sales means gross profit.",
                        "quote": "Net sales means gross profit.",
                        "location": "Net sales",
                    }
                ]
            },
        ),
        other,
        version_id,
    )
    _client(monkeypatch, FakeAi().reply("compare_facts", {"agree": False, "topic": "Net sales"}))
    compare_run(db_session, version_id, [doc_id, other], say=lambda *a, **k: None)
    db_session.commit()
    assert get_entry(db_session, version_id, key).confidence == "confirmed"
    facts = db_session.scalars(
        select(DocFact).where(DocFact.topic == "Net sales", DocFact.kind == "definition")
    ).all()
    assert all(fact.status == "conflicting" for fact in facts)
