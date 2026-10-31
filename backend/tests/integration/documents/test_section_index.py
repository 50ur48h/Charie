"""Section indexing: notes, vectors, the word index and resume (P08.4)."""

from decimal import Decimal

from sqlalchemy import func, select

from charie.learner.steps import document_index as index
from charie.learner.steps.document_index import INDEX_JOB, handle_index_document
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiError
from charie.shared.ai.fake import FakeAi
from charie.shared.jobs.registry import JobInfo
from charie.shared.search.embeddings import EmbeddingResult
from charie.shared.tables.sources import Document, DocumentSection

FIRST = ("Refunds", "# Refunds\n\nFull refunds within 30 days, code MEGA0926.\n")
SECOND = ("Shipping", "# Shipping\n\nShips in 2 days.\n")


def _add_indexed_doc(session, *, status="reading", sections=(FIRST, SECOND)) -> int:
    row = Document(
        file_name="guide.pdf",
        file_type="pdf",
        size_bytes=100,
        sha256="abc",
        status=status,
        progress=50,
    )
    session.add(row)
    session.flush()
    for position, (heading, text) in enumerate(sections):
        session.add(
            DocumentSection(
                document_id=row.id,
                position=position,
                heading_path=heading,
                text_=text,
            )
        )
    session.commit()
    return row.id


class _EmbedStub:
    """Records its inputs; optionally fails like a provider outage."""

    def __init__(self, error=None):
        self.batches: list[list[str]] = []
        self.error = error

    def embed_texts(self, texts, **kwargs):
        self.batches.append(list(texts))
        if self.error is not None:
            raise self.error
        return EmbeddingResult(
            vectors=[[1.0] + [0.0] * 1535 for _ in texts],
            prompt_tokens=len(texts),
            cost_usd=Decimal("0"),
        )


def _notes_client(monkeypatch, *notes: str) -> FakeAi:
    fake = FakeAi()
    for note in notes:
        fake.reply("note_section", {"note": note})
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(index, "get_ai", lambda: client)
    return fake


def _stub_embed(monkeypatch, error=None) -> _EmbedStub:
    stub = _EmbedStub(error)
    monkeypatch.setattr(index, "embeddings", stub)
    return stub


def _run(document_id: int, *, attempts: int = 3) -> None:
    handle_index_document(
        JobInfo(id=1, kind=INDEX_JOB, payload={"document_id": document_id}, attempts=attempts)
    )


def _sections(session, document_id: int) -> list[DocumentSection]:
    session.expire_all()
    return list(
        session.scalars(
            select(DocumentSection)
            .where(DocumentSection.document_id == document_id)
            .order_by(DocumentSection.position)
        )
    )


def test_note_section_notes_vectors_and_words(db_session, monkeypatch) -> None:
    doc_id = _add_indexed_doc(db_session)
    fake = _notes_client(monkeypatch, "Refund policy: 30 days.", "Shipping: 2 days.")
    stub = _stub_embed(monkeypatch)
    _run(doc_id)
    rows = _sections(db_session, doc_id)
    assert [section.note for section in rows] == [
        "Refund policy: 30 days.",
        "Shipping: 2 days.",
    ]
    assert all(len(section.embedding) == 1536 for section in rows)
    assert all(section.content_hash for section in rows)
    assert [call[0] for call in fake.calls] == ["note_section", "note_section"]
    assert stub.batches == [
        [
            "Refunds\n\nRefund policy: 30 days.\n\n" + FIRST[1],
            "Shipping\n\nShipping: 2 days.\n\n" + SECOND[1],
        ]
    ]
    found = db_session.scalars(
        select(DocumentSection).where(
            DocumentSection.search_text.op("@@")(func.plainto_tsquery("english", "MEGA0926"))
        )
    ).all()
    assert [section.id for section in found] == [rows[0].id]
    doc = db_session.get(Document, doc_id)
    assert (doc.progress, doc.error, doc.status) == (100, None, "reading")


def test_resume_skips_completed_sections(db_session, monkeypatch) -> None:
    doc_id = _add_indexed_doc(db_session)
    _notes_client(monkeypatch, "Refund policy: 30 days.", "Shipping: 2 days.")
    _stub_embed(monkeypatch, AiError("embed_down", "The embed call failed."))
    _run(doc_id)  # Notes land; vectors fail; the document fails but stays retryable.
    assert db_session.get(Document, doc_id).status == "failed"
    first = _sections(db_session, doc_id)
    assert [section.note for section in first] == ["Refund policy: 30 days.", "Shipping: 2 days."]
    assert all(section.embedding is None for section in first)
    fresh_fake = _notes_client(monkeypatch)  # No replies: notes must not be called again.
    stub = _stub_embed(monkeypatch)
    _run(doc_id)
    second = _sections(db_session, doc_id)
    assert [section.note for section in second] == [section.note for section in first]
    assert all(len(section.embedding) == 1536 for section in second)
    assert fresh_fake.calls == []  # Completed notes cost nothing the second time.
    assert len(stub.batches) == 1 and len(stub.batches[0]) == 2
    doc = db_session.get(Document, doc_id)
    assert (doc.status, doc.error) == ("reading", None)


def test_failure_not_learned(db_session, monkeypatch) -> None:
    doc_id = _add_indexed_doc(db_session)
    _notes_client(monkeypatch, "Refund policy: 30 days.", "Shipping: 2 days.")
    _stub_embed(monkeypatch, AiError("embed_down", "The embed call failed."))
    _run(doc_id)
    rows = _sections(db_session, doc_id)
    assert all(section.embedding is None for section in rows)  # Never a zero vector.
    assert all(section.note for section in rows)  # Notes stay for the resume.
    doc = db_session.get(Document, doc_id)
    assert doc.status == "failed" and doc.error == "The embed call failed."


def test_blank_note_rejected(db_session, monkeypatch) -> None:
    doc_id = _add_indexed_doc(db_session, sections=(FIRST,))
    _notes_client(monkeypatch, "   ")
    _stub_embed(monkeypatch)
    _run(doc_id)
    rows = _sections(db_session, doc_id)
    assert rows[0].note is None and rows[0].embedding is None
    assert db_session.get(Document, doc_id).status == "failed"


def test_learned_document_is_left_alone(db_session, monkeypatch) -> None:
    doc_id = _add_indexed_doc(db_session, status="learned")
    fake = _notes_client(monkeypatch)
    stub = _stub_embed(monkeypatch)
    _run(doc_id)
    assert fake.calls == [] and stub.batches == []
