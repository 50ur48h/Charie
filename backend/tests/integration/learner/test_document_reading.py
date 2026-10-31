"""Reading documents: jobs, sections and failure handling (P08.3)."""

from decimal import Decimal

import pytest

from charie.learner.steps import documents
from charie.learner.steps.base import StepContext
from charie.learner.steps.documents import (
    INDEX_JOB,
    NO_READABLE_TEXT,
    READ_JOB,
    make_jobs,
    run_job,
)
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiError, AiUnavailable
from charie.shared.ai.fake import FakeAi
from charie.shared.documents.reader import DocumentText
from charie.shared.jobs.queue import add_job
from charie.shared.jobs.registry import JobInfo
from charie.shared.search.embeddings import EmbeddingResult
from charie.shared.tables.learning import Job
from charie.shared.tables.sources import Document, DocumentFile, DocumentSection

MARKDOWN = "# Refunds\n\nFull refunds within 30 days.\n\n## Exceptions\n\nFinal sale items.\n"


def _add_document(session, *, file_type="md", content=None, status="new") -> int:
    content = content if content is not None else MARKDOWN.encode("utf-8")
    row = Document(
        file_name=f"guide.{file_type}",
        file_type=file_type,
        size_bytes=len(content),
        sha256="abc",
        status=status,
    )
    session.add(row)
    session.flush()
    session.add(DocumentFile(document_id=row.id, content=content))
    session.commit()
    return row.id


def _ctx(session) -> tuple[StepContext, list]:
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    ctx = StepContext(
        session=session,
        run_id=1,
        version_id=1,
        source=None,
        connector=None,
        strict_mode=False,
        settings={},
        say=say,
    )
    return ctx, said


def _info(document_id: int, *, attempts: int = 1) -> JobInfo:
    return JobInfo(
        id=1,
        kind=READ_JOB,
        payload={"document_id": document_id},
        run_id=1,
        attempts=attempts,
    )


def _index_fakes(monkeypatch) -> None:
    """Fake the index seams; the index job has its own tests."""
    from charie.learner.steps import document_index

    fake = (
        FakeAi()
        .reply("note_section", {"note": "Refunds."})
        .reply("note_section", {"note": "Exceptions."})
    )
    monkeypatch.setattr(
        document_index,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )

    class StubEmbed:
        def embed_texts(self, texts, **kwargs):
            return EmbeddingResult(
                vectors=[[1.0] + [0.0] * 1535 for _ in texts],
                prompt_tokens=0,
                cost_usd=Decimal("0"),
            )

    monkeypatch.setattr(document_index, "embeddings", StubEmbed())


def _stub_read(monkeypatch, result=None, error=None):
    def fake_read(data: bytes, **kwargs) -> DocumentText:
        if error is not None:
            raise error
        assert result is not None
        return result

    monkeypatch.setattr(documents.reader, "read_document", fake_read)
    _index_fakes(monkeypatch)


def test_make_jobs_only_new_without_active_read(db_session) -> None:
    fresh = _add_document(db_session, status="new")
    _add_document(db_session, status="failed")
    _add_document(db_session, status="learned")
    _add_document(db_session, status="removed")
    busy = _add_document(db_session, status="new")
    add_job(db_session, READ_JOB, {"document_id": busy})
    db_session.commit()
    ctx, _ = _ctx(db_session)
    assert make_jobs(ctx) == [{"document_id": fresh}]


def test_read_indexes_inline_in_run(db_session, monkeypatch) -> None:

    doc_id = _add_document(db_session, file_type="pdf", content=b"%PDF-fake")
    _stub_read(
        monkeypatch,
        DocumentText(filename="guide.pdf", markdown=MARKDOWN, page_count=2, cost_usd=Decimal("0")),
    )
    ctx, said = _ctx(db_session)
    run_job(_info(doc_id), ctx)
    db_session.commit()
    doc = db_session.get(Document, doc_id)
    assert doc.status == "reading"
    assert doc.pages == 2
    assert doc.unreadable_pages == 0
    assert doc.progress == 100  # Read and indexed in one in-run pass.
    assert doc.error is None
    sections = (
        db_session.query(DocumentSection)
        .filter(DocumentSection.document_id == doc_id)
        .order_by(DocumentSection.position)
        .all()
    )
    assert [section.heading_path for section in sections] == ["Refunds", "Refunds > Exceptions"]
    assert sections[0].page_from is None  # No page marks in a multi-page read.
    assert ("found", "Read guide.pdf: 2 section(s).") in said
    assert all(section.note for section in sections)
    assert all(section.embedding is not None for section in sections)
    assert db_session.query(Job).filter(Job.kind == INDEX_JOB).count() == 0  # No chain needed.


def test_standalone_read_queues_index(db_session, monkeypatch) -> None:
    from charie.learner.steps.documents import process_document

    doc_id = _add_document(db_session, file_type="pdf", content=b"%PDF-fake")
    _stub_read(
        monkeypatch,
        DocumentText(filename="guide.pdf", markdown=MARKDOWN, page_count=2, cost_usd=Decimal("0")),
    )
    said: list = []
    process_document(
        db_session,
        db_session.get(Document, doc_id),
        say=lambda kind, message, details=None: said.append((kind, message)),
        learning_run_id=None,
    )
    db_session.commit()
    assert db_session.get(Document, doc_id).progress == 50
    jobs = db_session.query(Job).filter(Job.kind == INDEX_JOB).all()
    assert len(jobs) == 1 and jobs[0].payload["document_id"] == doc_id


def test_md_decodes_locally_without_ai(db_session, monkeypatch) -> None:
    _index_fakes(monkeypatch)
    doc_id = _add_document(db_session, file_type="md")
    ctx, _ = _ctx(db_session)
    run_job(_info(doc_id), ctx)  # No read stub: Markdown never touches the provider.
    db_session.commit()
    assert db_session.get(Document, doc_id).pages == 0
    count = db_session.query(DocumentSection).filter(DocumentSection.document_id == doc_id).count()
    assert count == 2


def test_retry_atomic_keeps_old_sections(db_session, monkeypatch) -> None:
    doc_id = _add_document(db_session, file_type="pdf", content=b"%PDF-fake", status="failed")
    old = DocumentSection(document_id=doc_id, position=0, heading_path="Old", text_="Old text.")
    db_session.add(old)
    db_session.commit()
    _stub_read(monkeypatch, error=AiUnavailable())
    ctx, said = _ctx(db_session)
    run_job(_info(doc_id, attempts=3), ctx)  # Last try: the document fails, no raise.
    db_session.commit()
    doc = db_session.get(Document, doc_id)
    assert doc.status == "failed"
    assert "try again" in (doc.error or "")
    sections = db_session.query(DocumentSection).filter(DocumentSection.document_id == doc_id).all()
    assert len(sections) == 1 and sections[0].text_ == "Old text."  # No duplicates.
    assert db_session.query(Job).filter(Job.kind == INDEX_JOB).count() == 0
    assert any(kind == "warning" for kind, _ in said)


def test_transient_failure_reraises_before_last_try(db_session, monkeypatch) -> None:
    doc_id = _add_document(db_session, file_type="pdf", content=b"%PDF-fake")
    _stub_read(monkeypatch, error=AiError("di_bad_replay", "The saved read is damaged."))
    ctx, _ = _ctx(db_session)
    with pytest.raises(AiError):
        run_job(_info(doc_id, attempts=1), ctx)
    assert db_session.get(Document, doc_id).error is None  # Not failed yet.


def test_unreadable_pages_warn(db_session, monkeypatch) -> None:
    doc_id = _add_document(db_session, file_type="pdf", content=b"%PDF-fake")
    _stub_read(
        monkeypatch,
        DocumentText(
            filename="guide.pdf",
            markdown="# Only\n\nOne readable page.\n",
            page_count=3,
            cost_usd=Decimal("0"),
            unreadable_pages=2,
        ),
    )
    ctx, said = _ctx(db_session)
    run_job(_info(doc_id), ctx)
    db_session.commit()
    assert db_session.get(Document, doc_id).unreadable_pages == 2
    assert ("warning", "2 page(s) couldn't be read.") in said


def test_no_readable_text_fails_plainly(db_session, monkeypatch) -> None:
    doc_id = _add_document(db_session, file_type="pdf", content=b"%PDF-fake")
    _stub_read(
        monkeypatch,
        DocumentText(filename="guide.pdf", markdown="  \n", page_count=2, cost_usd=Decimal("0")),
    )
    ctx, said = _ctx(db_session)
    run_job(_info(doc_id), ctx)
    db_session.commit()
    doc = db_session.get(Document, doc_id)
    assert doc.status == "failed"
    assert doc.error == NO_READABLE_TEXT
    assert ("warning", f"Couldn't read guide.pdf: {NO_READABLE_TEXT}") in said
    count = db_session.query(DocumentSection).filter(DocumentSection.document_id == doc_id).count()
    assert count == 0


def test_removed_document_is_left_alone(db_session, monkeypatch) -> None:
    doc_id = _add_document(db_session, status="removed")
    _stub_read(monkeypatch, error=AiUnavailable())
    ctx, _ = _ctx(db_session)
    run_job(_info(doc_id), ctx)  # Returns quietly; nothing to read.
    assert db_session.get(Document, doc_id).status == "removed"
