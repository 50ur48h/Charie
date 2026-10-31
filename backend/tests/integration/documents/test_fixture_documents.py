"""P08.7 fixture documents: converted reads, exact quotes, conflict, period.

The two fixture files go through the real reader with a local OOXML
converter standing in for Layout (no network, no credentials), then the
real splitter and fact steps. Fake AI replies keep CI free.
"""

import io
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from charie.learner.steps import doc_facts
from charie.learner.steps.base import StepContext
from charie.learner.steps.doc_facts import compare_run, run_job
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.documents import reader
from charie.shared.documents.sections import split_sections
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge.store import get_entry
from charie.shared.knowledge.versions import get_or_create_draft
from charie.shared.search import search as search_mod
from charie.shared.search.embeddings import EmbeddingResult
from charie.shared.tables.knowledge import KbEntry
from charie.shared.tables.sources import DocFact, Document, DocumentSection

DATA = Path(__file__).resolve().parents[2] / "data" / "documents"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _local_docx_analyze(data: bytes) -> tuple[str, int]:
    """Stdlib paragraphs and tables; the test's stand-in for Layout."""
    root = ET.fromstring(zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml"))
    blocks: list[str] = []
    for child in root.find(W + "body"):
        if child.tag == W + "p":
            style = child.find(W + "pPr/" + W + "pStyle")
            text = "".join(node.text or "" for node in child.iter(W + "t")).strip()
            if not text:
                continue
            if style is not None and (style.get(W + "val") or "").startswith("Heading"):
                blocks.append("# " + text)
            else:
                blocks.append(text)
        elif child.tag == W + "tbl":
            for row in child.findall(W + "tr"):
                cells = [
                    "".join(node.text or "" for node in cell.iter(W + "t")).strip()
                    for cell in row.findall(W + "tc")
                ]
                blocks.append("| " + " | ".join(cells) + " |")
    return (chr(10) + chr(10)).join(blocks) + chr(10), 1


def _read(name: str) -> str:
    doc = reader.read_document(
        (DATA / name).read_bytes(),
        filename=name,
        cost_log=MemoryCostLog(),
        _analyze=_local_docx_analyze,
    )
    assert doc.page_count == 1
    return doc.markdown


class _EmbedStub:
    def embed_texts(self, texts, **kwargs):
        return EmbeddingResult(
            vectors=[[1.0] + [0.0] * 1535 for _ in texts],
            prompt_tokens=len(texts),
            cost_usd=Decimal("0"),
        )


def _add_doc(session, name: str) -> int:
    row = Document(file_name=name, file_type="docx", size_bytes=10, sha256=name, status="reading")
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


def _run_extract(session, monkeypatch, fake, doc_id, version_id):
    _client(monkeypatch, fake)
    ctx, said = _ctx(session, version_id)
    info = JobInfo(id=1, kind="extract_doc_facts", payload={"document_id": doc_id}, run_id=1)
    run_job(info, ctx)
    session.commit()
    return said


def _section_with(markdown: str, needle: str) -> tuple[str, str]:
    found = [draft for draft in split_sections(markdown, page_count=1) if needle in draft.text]
    assert len(found) == 1
    return found[0].heading_path, found[0].text


NET_SALES_DEF = "Net sales means total orders minus refunds."
NET_SALES_FORMULA = "Net sales equals total orders minus refunds."
NET_SALES_2025 = "Net sales were $1.2M in 2025."
CHECKOUT_CODE = "Use code MEGA0926 at checkout."
GROSS_PROFIT_DEF = "Net sales means gross profit."
POLICY_2025 = "Net sales were $1.5M in 2025."


def _extract_replies(heading_def: str, heading_code: str) -> FakeAi:
    return (
        FakeAi()
        .reply(
            "extract_doc_facts",
            {
                "facts": [
                    {
                        "kind": "definition",
                        "topic": "Net sales",
                        "statement": NET_SALES_DEF,
                        "quote": NET_SALES_DEF,
                        "location": heading_def,
                    },
                    {
                        "kind": "reported_number",
                        "topic": "Net sales 2025",
                        "statement": NET_SALES_2025,
                        "quote": NET_SALES_2025,
                        "location": heading_def,
                    },
                ]
            },
        )
        .reply(
            "extract_doc_facts",
            {
                "facts": [
                    {
                        "kind": "code",
                        "topic": "Checkout code",
                        "statement": "MEGA0926 is the checkout code.",
                        "quote": CHECKOUT_CODE,
                        "location": heading_code,
                    }
                ]
            },
        )
    )


def test_quotes_and_conflict(db_session, monkeypatch) -> None:
    finance = _read("finance-definitions.docx")
    policy = _read("conflicting-policy.docx")
    for quote in (NET_SALES_DEF, NET_SALES_FORMULA, NET_SALES_2025, CHECKOUT_CODE):
        assert quote in finance
    assert "Margherita" in finance and "18.00" in finance
    for quote in (GROSS_PROFIT_DEF, POLICY_2025, "Final sale items can be refunded"):
        assert quote in policy
    version = get_or_create_draft(db_session, "first_learning")
    fin_id = _add_doc(db_session, "finance-definitions.docx")
    heading_def, text_def = _section_with(finance, NET_SALES_DEF)
    heading_code, text_code = _section_with(finance, CHECKOUT_CODE)
    _add_section(db_session, fin_id, 0, heading_def, text_def)
    _add_section(db_session, fin_id, 1, heading_code, text_code)
    pol_id = _add_doc(db_session, "conflicting-policy.docx")
    heading_pol, text_pol = _section_with(policy, GROSS_PROFIT_DEF)
    _add_section(db_session, pol_id, 0, heading_pol, text_pol)
    db_session.commit()
    _run_extract(
        db_session, monkeypatch, _extract_replies(heading_def, heading_code), fin_id, version.id
    )
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
                        "statement": GROSS_PROFIT_DEF,
                        "quote": GROSS_PROFIT_DEF,
                        "location": heading_pol,
                    },
                    {
                        "kind": "reported_number",
                        "topic": "Net sales 2025",
                        "statement": POLICY_2025,
                        "quote": POLICY_2025,
                        "location": heading_pol,
                    },
                ]
            },
        ),
        pol_id,
        version.id,
    )
    _client(
        monkeypatch,
        FakeAi()
        .reply("compare_facts", {"agree": False, "topic": "Net sales"})
        .reply("compare_facts", {"agree": False, "topic": "Net sales 2025"}),
    )
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    conflicts = compare_run(db_session, version.id, [fin_id, pol_id], say=say)
    db_session.commit()
    assert conflicts == ["Net sales", "Net sales 2025"]
    defs = db_session.scalars(
        select(DocFact).where(DocFact.topic == "Net sales", DocFact.kind == "definition")
    ).all()
    assert len(defs) == 2 and all(fact.status == "conflicting" for fact in defs)
    assert all(fact.quote in (NET_SALES_DEF, GROSS_PROFIT_DEF) for fact in defs)
    codes = db_session.scalars(select(DocFact).where(DocFact.kind == "code")).all()
    assert len(codes) == 1 and codes[0].quote == CHECKOUT_CODE
    fin_entry = get_entry(db_session, version.id, f"doc.definition.net_sales.{fin_id}")
    assert fin_entry is not None and fin_entry.confidence == "conflicting"
    assert any(kind == "warning" and "Conflict in Net sales" in message for kind, message in said)


def test_reported_period(db_session, monkeypatch) -> None:
    finance = _read("finance-definitions.docx")
    assert NET_SALES_2025 in finance
    version = get_or_create_draft(db_session, "first_learning")
    fin_id = _add_doc(db_session, "finance-definitions.docx")
    heading_def, text_def = _section_with(finance, NET_SALES_DEF)
    _add_section(db_session, fin_id, 0, heading_def, text_def)
    db_session.commit()
    fake = FakeAi().reply(
        "extract_doc_facts",
        {
            "facts": [
                {
                    "kind": "reported_number",
                    "topic": "Net sales 2025",
                    "statement": NET_SALES_2025,
                    "quote": NET_SALES_2025,
                    "location": heading_def,
                }
            ]
        },
    )
    _run_extract(db_session, monkeypatch, fake, fin_id, version.id)
    rows = db_session.scalars(
        select(DocFact).where(DocFact.document_id == fin_id, DocFact.kind == "reported_number")
    ).all()
    assert len(rows) == 1
    assert rows[0].statement == NET_SALES_2025 and rows[0].quote == NET_SALES_2025
    assert "2025" in rows[0].statement
    assert get_entry(db_session, version.id, f"doc.reported_number.net_sales_2025.{fin_id}") is None
    assert db_session.scalar(select(func.count()).select_from(KbEntry)) == 0
