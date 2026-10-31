"""Document uploads, listing, removal and retry (P08.2)."""

import hashlib

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from charie.shared.db import get_session
from charie.shared.documents import uploads
from charie.shared.errors import ApiError
from charie.shared.jobs.queue import add_job
from charie.shared.tables.learning import Job
from charie.shared.tables.sources import Document, DocumentFile

documents_router = APIRouter(prefix="/api/documents", tags=["documents"])

READ_JOB = "read_document"


class DocumentOut(BaseModel):
    """One row for the Sources table; nulls mean not known yet."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    file_type: str
    size_bytes: int
    pages: int | None
    unreadable_pages: int
    fact_count: int
    status: str
    progress: int | None
    error: str | None
    uploaded_at: str
    learned_at: str | None


class DocumentEnvelope(BaseModel):
    document: DocumentOut


class DocumentListEnvelope(BaseModel):
    documents: list[DocumentOut]


def _shape(row: Document) -> DocumentOut:
    # Pages and progress are unknown until the reader counts them.
    return DocumentOut(
        id=row.id,
        file_name=row.file_name,
        file_type=row.file_type,
        size_bytes=row.size_bytes,
        pages=row.pages or None,
        unreadable_pages=row.unreadable_pages,
        fact_count=row.fact_count,
        status=row.status,
        progress=row.progress if row.status == "reading" else None,
        error=row.error,
        uploaded_at=row.uploaded_at.isoformat(),
        learned_at=row.learned_at.isoformat() if row.learned_at else None,
    )


def queue_reading(session, document_id: int) -> None:
    """Queue a read unless one is already waiting or running for it."""
    waiting = session.scalars(
        select(Job).where(
            Job.kind == READ_JOB,
            Job.status.in_(("queued", "running")),
        )
    ).all()
    if any((job.payload or {}).get("document_id") == document_id for job in waiting):
        return
    add_job(session, READ_JOB, {"document_id": document_id})


@documents_router.get("", response_model=DocumentListEnvelope)
def list_documents(session=Depends(get_session)):  # type: ignore[no-untyped-def]
    """Every document except removed ones, newest first."""
    rows = session.scalars(
        select(Document).where(Document.status != "removed").order_by(Document.id.desc())
    ).all()
    return {"documents": [_shape(row) for row in rows]}


@documents_router.post("", response_model=DocumentEnvelope)
async def upload_document(file: UploadFile, session=Depends(get_session)):  # type: ignore[no-untyped-def]
    """Save one file with its bytes and queue its first read."""
    file_name = uploads.clean_name(file.filename)
    file_type = uploads.file_type_of(file_name)
    uploads.check_type(file_type, file_name)
    raw = await uploads.read_bytes(file, file_name)
    uploads.check_bytes(file_type, raw, file_name)
    digest = hashlib.sha256(raw).hexdigest()
    existing = session.scalars(
        select(Document).where(Document.sha256 == digest, Document.status != "removed")
    ).first()
    if existing is not None:
        return JSONResponse(
            content={"document": _shape(existing).model_dump(mode="json")},
            status_code=200,
        )
    row = Document(
        file_name=file_name,
        file_type=file_type,
        size_bytes=len(raw),
        sha256=digest,
        status="new",
    )
    session.add(row)
    session.flush()
    session.add(DocumentFile(document_id=row.id, content=raw))
    queue_reading(session, row.id)
    session.commit()
    return JSONResponse(content={"document": _shape(row).model_dump(mode="json")}, status_code=201)


@documents_router.delete("/{document_id}", status_code=204)
def remove_document(document_id: int, session=Depends(get_session)):  # type: ignore[no-untyped-def]
    """Mark removed; the row stays so the next refresh sees the removal."""
    row = session.get(Document, document_id)
    if row is None or row.status == "removed":
        raise ApiError(404, "not_found", "Charie couldn't find that document.")
    row.status = "removed"
    session.commit()
    return Response(status_code=204)


@documents_router.post("/{document_id}/retry", response_model=DocumentEnvelope)
def retry_document(document_id: int, session=Depends(get_session)):  # type: ignore[no-untyped-def]
    """Try a failed document again; finished documents have nothing to retry."""
    row = session.get(Document, document_id)
    if row is None or row.status == "removed":
        raise ApiError(404, "not_found", "Charie couldn't find that document.")
    if row.status != "failed" and row.unreadable_pages == 0:
        raise ApiError(409, "nothing_to_retry", "This document doesn't need another try.")
    row.status = "new"
    row.error = None
    row.progress = 0
    row.pages = 0
    row.unreadable_pages = 0
    row.learned_at = None
    queue_reading(session, row.id)
    session.commit()
    return {"document": _shape(row)}
