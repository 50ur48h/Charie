"""Business term discovery from learned evidence (P09.3, fake AI)."""

from charie.learner.steps import business_numbers
from charie.learner.steps.base import StepContext
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.sources import DocFact, Document, DocumentSection


def _seed(db_session) -> int:
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    store.upsert_entry(
        db_session,
        version_id,
        "table.shop.orders",
        "table",
        "orders",
        "One row per order the shop took.",
        {"schema": "shop", "name": "orders", "grain": "one order"},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "column.shop.orders.total_amount",
        "column",
        "total_amount",
        "What the customer paid, in dollars.",
        {
            "schema": "shop",
            "table": "orders",
            "name": "total_amount",
            "data_type": "numeric",
            "unit": "money",
            "currency": "USD",
        },
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    store.upsert_entry(
        db_session,
        version_id,
        "rule.no_test_restaurants",
        "rule",
        "Test restaurants never count",
        "Test restaurants never count unless asked.",
        {
            "rule_type": "always_filter",
            "table": "shop.restaurants",
            "column": "is_test",
            "values": ["false"],
        },
        "confirmed",
        [{"type": "owner_notes", "quote": "Test restaurants never count"}],
        "seed",
    )
    doc = Document(
        file_name="guide.md", file_type="md", size_bytes=10, sha256="abc", status="learned"
    )
    db_session.add(doc)
    db_session.flush()
    section = DocumentSection(document_id=doc.id, position=0, text_="Net sales defined.")
    db_session.add(section)
    db_session.flush()
    db_session.add(
        DocFact(
            document_id=doc.id,
            section_id=section.id,
            kind="definition",
            topic="Net sales",
            statement="Net sales means completed order totals.",
            quote="Net sales means completed order totals.",
            status="ok",
        )
    )
    db_session.commit()
    return version_id


def _ctx(db_session, version_id: int):
    run = LearningRun(
        kind="first", status="running", step="business_numbers", version_id=version_id
    )
    db_session.add(run)
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    ctx = StepContext(
        session=db_session,
        run_id=run.id,
        version_id=version_id,
        source=None,
        connector=None,
        strict_mode=False,
        settings={},
        say=say,
    )
    return ctx, said, run


def _run(ctx, monkeypatch, reply: dict) -> FakeAi:
    fake = FakeAi().reply("find_business_terms", reply)
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(business_numbers, "get_ai", lambda: client)
    business_numbers.run_job(
        JobInfo(
            id=1,
            kind="find_business_terms",
            payload={"step": "business_numbers"},
            run_id=ctx.run_id,
        ),
        ctx,
    )
    return fake


def _term(name: str, **overrides) -> dict:
    term = {
        "name": name,
        "meaning": f"{name} for the period.",
        "unit": "money",
        "evidence": ["column:shop.orders.total_amount"],
        "splits": ["by month"],
    }
    term.update(overrides)
    return term


def test_evidence_required(db_session, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, said, _ = _ctx(db_session, version_id)
    _run(
        ctx,
        monkeypatch,
        {
            "terms": [
                _term(
                    "Net sales",
                    evidence=["column:shop.orders.total_amount", "doc:Net sales"],
                ),
                _term("Ghost sales", evidence=["table:shop.missing"]),
            ]
        },
    )
    proposals = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]["proposals"]
    assert [proposal["name"] for proposal in proposals] == ["Net sales"]
    assert any("without real evidence" in message for _, message in said)


def test_duplicate_resume(db_session, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, _, _ = _ctx(db_session, version_id)
    _run(
        ctx,
        monkeypatch,
        {
            "terms": [
                _term("Net sales", splits=["by month"]),
                _term(
                    "net sales ",
                    splits=["by restaurant"],
                    evidence=["table:shop.orders", "rule:Test restaurants never count"],
                ),
            ]
        },
    )
    db_session.expire_all()
    proposals = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]["proposals"]
    assert len(proposals) == 1
    assert sorted(proposals[0]["splits"]) == ["by month", "by restaurant"]
    assert sorted(proposals[0]["evidence"]) == [
        "column:shop.orders.total_amount",
        "rule:Test restaurants never count",
        "table:shop.orders",
    ]
    # Resuming finds the proposals and queues nothing new.
    assert business_numbers.make_jobs(ctx) == []


def test_candidates_not_usable(db_session, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, _, _ = _ctx(db_session, version_id)
    _run(ctx, monkeypatch, {"terms": [_term("Net sales")]})
    db_session.expire_all()
    proposals = db_session.get(LearningRun, ctx.run_id).progress["business_numbers"]["proposals"]
    assert proposals and all(proposal["proposed"] for proposal in proposals)
    assert store.list_entries(db_session, version_id, kinds=["metric"]) == []
