"""Upload to searchable, and honest about where it stopped (architecture 5.5)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from charie.config import Settings, get_settings
from charie.db.models import KnowledgeChunk, KnowledgeDocument
from charie.knowledge.chunking import chunk_document
from charie.knowledge.embeddings import Embedder, embed_texts
from charie.knowledge.extract import ExtractionError, extract_text
from charie.knowledge.store import DocumentStore
from charie.llm.base import LLMError
from charie.tenancy.session import org_session

__all__ = [
    "DocumentView",
    "ingest_document",
    "list_documents",
    "reindex_document",
    "unembedded_chunks",
]

STATUS_PENDING = "pending"
STATUS_INDEXED = "indexed"
STATUS_FAILED = "failed"

#: How much of a failure's detail reaches the column, which is rendered to a person.
REASON_LIMIT = 500


@dataclass(frozen=True, slots=True)
class DocumentView:
    """A document as a caller sees it."""

    id: uuid.UUID
    title: str
    mime: str
    status: str
    chunk_count: int
    failure_reason: str | None
    created_at: datetime
    indexed_at: datetime | None
    #: How many of this document's chunks have a vector.
    embedded_count: int = 0


async def ingest_document(
    *,
    org_id: uuid.UUID,
    title: str,
    payload: bytes,
    mime: str,
    store: DocumentStore,
    embedder: Embedder | None = None,
    filename: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> DocumentView:
    """Take an upload all the way to searchable, or record why it stopped."""
    resolved = settings if settings is not None else get_settings()

    document_id = uuid.uuid4()
    reference = await store.put(org_id=org_id, document_id=document_id, payload=payload, mime=mime)

    async with org_session(org_id) as session:
        session.add(
            KnowledgeDocument(
                id=document_id,
                org_id=org_id,
                title=title[:300],
                blob_path=reference,
                mime=mime,
                status=STATUS_PENDING,
                created_by=actor_user_id,
            )
        )
        await session.flush()

    try:
        text = extract_text(payload, mime=mime, filename=filename)
    except ExtractionError as error:
        # The one failure that is the file's fault rather than the platform's.
        return await _fail(org_id, document_id, str(error))

    return await _index(
        org_id=org_id,
        document_id=document_id,
        text=text,
        embedder=embedder,
        actor_user_id=actor_user_id,
        settings=resolved,
    )


async def reindex_document(
    *,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    store: DocumentStore,
    embedder: Embedder | None = None,
    actor_user_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> DocumentView:
    """Chunk and embed a stored document again, from its original bytes."""
    resolved = settings if settings is not None else get_settings()

    async with org_session(org_id) as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:
            raise LookupError("No such document")
        reference, mime = document.blob_path, document.mime

    payload = await store.get(org_id=org_id, reference=reference)
    if payload is None:
        return await _fail(
            org_id,
            document_id,
            "The original file is no longer in storage, so it cannot be re-read.",
        )

    try:
        text = extract_text(payload, mime=mime)
    except ExtractionError as error:
        return await _fail(org_id, document_id, str(error))

    return await _index(
        org_id=org_id,
        document_id=document_id,
        text=text,
        embedder=embedder,
        actor_user_id=actor_user_id,
        settings=resolved,
    )


async def _index(
    *,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    text: str,
    embedder: Embedder | None,
    actor_user_id: uuid.UUID | None,
    settings: Settings,
) -> DocumentView:
    """Chunk, write, embed — in that order, and each step survivable."""
    chunks = chunk_document(text)
    if not chunks:
        return await _fail(org_id, document_id, "This file produced no text to index.")

    # Delete then write, in one transaction.
    async with org_session(org_id) as session:
        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        )
        for chunk in chunks:
            session.add(
                KnowledgeChunk(
                    org_id=org_id,
                    document_id=document_id,
                    seq=chunk.seq,
                    text_=chunk.text,
                    headings=list(chunk.headings),
                    token_estimate=chunk.token_estimate,
                )
            )
        await session.flush()

    if embedder is not None:
        try:
            vectors = await embed_texts(
                org_id=org_id,
                texts=[chunk.text for chunk in chunks],
                embedder=embedder,
                actor_user_id=actor_user_id,
                settings=settings,
            )
        except LLMError as error:
            # The text is already stored and already lexically searchable.
            return await _fail(
                org_id, document_id, f"The text was stored but not embedded: {error}"
            )

        async with org_session(org_id) as session:
            rows = (
                (
                    await session.execute(
                        select(KnowledgeChunk)
                        .where(KnowledgeChunk.document_id == document_id)
                        .order_by(KnowledgeChunk.seq)
                    )
                )
                .scalars()
                .all()
            )
            # Paired by position, which is safe only because `embed_texts` guarantees one vector...
            for row, vector in zip(rows, vectors, strict=True):
                row.embedding = list(vector)

    return await _finish(org_id, document_id, len(chunks))


async def _finish(org_id: uuid.UUID, document_id: uuid.UUID, chunk_count: int) -> DocumentView:
    async with org_session(org_id) as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:  # pragma: no cover - it was written moments ago
            raise LookupError("No such document")
        document.status = STATUS_INDEXED
        document.failure_reason = None
        document.chunk_count = chunk_count
        document.indexed_at = datetime.now(UTC)
        await session.flush()
        return await _view(session, document)


async def _fail(org_id: uuid.UUID, document_id: uuid.UUID, reason: str) -> DocumentView:
    """Record the stop, with a reason the CHECK constraint insists on."""
    async with org_session(org_id) as session:
        document = await session.get(KnowledgeDocument, document_id)
        if document is None:  # pragma: no cover - it was written moments ago
            raise LookupError("No such document")
        document.status = STATUS_FAILED
        document.failure_reason = reason[:REASON_LIMIT]
        document.chunk_count = await _count_chunks(session, document_id)
        await session.flush()
        return await _view(session, document)


async def _count_chunks(session: AsyncSession, document_id: uuid.UUID) -> int:
    total = (
        await session.execute(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
        )
    ).scalar_one()
    return int(total)


async def _view(session: AsyncSession, document: KnowledgeDocument) -> DocumentView:
    embedded = (
        await session.execute(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.embedding.isnot(None),
            )
        )
    ).scalar_one()
    return DocumentView(
        id=document.id,
        title=document.title,
        mime=document.mime,
        status=document.status,
        chunk_count=document.chunk_count,
        failure_reason=document.failure_reason,
        created_at=document.created_at,
        indexed_at=document.indexed_at,
        embedded_count=int(embedded),
    )


async def list_documents(*, org_id: uuid.UUID) -> list[DocumentView]:
    """Every document this organization has, newest first."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [await _view(session, row) for row in rows]


async def unembedded_chunks(*, org_id: uuid.UUID, limit: int = 500) -> Sequence[uuid.UUID]:
    """The backfill's work list, straight off the partial index (revision 0016)."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(KnowledgeChunk.id)
                    .where(KnowledgeChunk.embedding.is_(None))
                    .order_by(KnowledgeChunk.created_at)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)
