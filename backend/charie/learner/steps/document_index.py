"""Section indexing: one-line notes and meaning vectors (P08.4).

A standalone `index_document` job follows each successful read: notes come
from the common AI client, vectors from the shared embedding helper in
bounded batches. Each section checkpoints on its content hash, so an
interrupted run resumes the remaining sections without paying again for
finished ones. `learned` is still set later: facts arrive in P08.6.
"""

import hashlib

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.learner.steps.documents import INDEX_JOB
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import AiError, AiFormError, SpendingPaused
from charie.shared.db import session_scope
from charie.shared.jobs.registry import JobInfo, job_handler
from charie.shared.search import embeddings
from charie.shared.tables.sources import Document, DocumentSection

NOTE_JOB = "note_section"

INDEX_FAILED = "Something went wrong while indexing it."


class SectionNoteForm(BaseModel):
    """The fixed form the note job answers in."""

    model_config = ConfigDict(extra="forbid")

    note: str = Field(description="One line saying what the section is about.")


def content_hash(heading_path: str | None, text: str) -> str:
    """The checkpoint key: what the section said, not the note about it."""
    return hashlib.sha256(f"{heading_path or ''}\n{text}".encode()).hexdigest()


def embed_text(section: DocumentSection) -> str:
    """What gets embedded: heading, note and text together."""
    return "\n\n".join(part for part in [section.heading_path, section.note, section.text_] if part)


def _plain_error(err: Exception) -> str:
    if isinstance(err, AiError):
        return err.message
    return INDEX_FAILED


def index_document(session: Session, doc: Document, *, learning_run_id: int | None) -> None:
    """Note and embed one document's sections, committing as it goes."""
    sections = session.scalars(
        select(DocumentSection)
        .where(DocumentSection.document_id == doc.id)
        .order_by(DocumentSection.position)
    ).all()
    if not sections:
        return
    client = get_ai()
    for section in sections:
        hashed = content_hash(section.heading_path, section.text_)
        if section.content_hash == hashed and section.note:
            continue
        form = client.run(
            NOTE_JOB,
            {"section": section.text_},
            SectionNoteForm,
            app="learner",
            learning_run_id=learning_run_id,
        )
        if not form.note.strip():
            raise AiFormError(NOTE_JOB)
        section.note = form.note.strip()
        section.content_hash = hashed
        session.commit()
    pending = [
        section
        for section in session.scalars(
            select(DocumentSection)
            .where(DocumentSection.document_id == doc.id)
            .order_by(DocumentSection.position)
        )
        if section.content_hash != content_hash(section.heading_path, section.text_)
        or section.embedding is None
    ]
    if pending:
        result = embeddings.embed_texts(
            [embed_text(section) for section in pending],
            app="learner",
            learning_run_id=learning_run_id,
        )
        for section, vector in zip(pending, result.vectors, strict=True):
            section.embedding = vector
            section.content_hash = content_hash(section.heading_path, section.text_)
        session.commit()
    doc.progress = 100
    doc.error = None
    if doc.status == "failed":
        doc.status = "reading"  # The resume finished; facts still land in P08.6.
    session.commit()


@job_handler(INDEX_JOB)
def handle_index_document(info: JobInfo) -> None:
    """Index one document; a final failure marks it failed but retryable."""
    with session_scope() as session:
        doc = session.get(Document, (info.payload or {}).get("document_id"))
        if doc is None or doc.status in ("removed", "learned"):
            return
        try:
            index_document(
                session, doc, learning_run_id=(info.payload or {}).get("learning_run_id")
            )
        except SpendingPaused:
            raise
        except Exception as err:  # noqa: BLE001 (same retry rule as reading)
            if info.attempts >= 3:
                doc.status = "failed"
                doc.error = _plain_error(err)
                return
            raise
