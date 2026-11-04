"""Documents API (architecture Part 10.2, plan WP10.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from charie.auth.context import RequestContext
from charie.auth.guards import require_contributor, require_member
from charie.config import get_settings
from charie.db.models import KnowledgeDocument
from charie.knowledge import embeddings, ingest
from charie.knowledge.embeddings import Embedder
from charie.knowledge.extract import SUPPORTED_MIME
from charie.knowledge.retrieve import search_knowledge
from charie.knowledge.store import DocumentStore, LocalDocumentStore
from charie.tenancy.session import org_session

router = APIRouter(prefix="/v1", tags=["knowledge"])

DocumentId = Annotated[uuid.UUID, Path(description="Document within this organization")]

#: A ceiling on one upload, in bytes.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def document_store() -> DocumentStore:
    """The store this deployment uses. One line to change in Phase 12 (B-072)."""
    return LocalDocumentStore(get_settings().artifacts_path / "documents")


def document_embedder() -> Embedder | None:
    """The embedder these routes ingest and search with, or None (B-073)."""
    return embeddings.get_embedder()


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    mime: str
    status: str = Field(description="pending | indexed | failed")
    chunk_count: int
    embedded_count: int = Field(
        description=(
            "How many chunks carry a vector. Below chunk_count means the text is "
            "searchable by wording but not yet by meaning — a real and temporary "
            "state, not an error."
        )
    )
    failure_reason: str | None = Field(
        default=None,
        description="Why indexing stopped, in words for the person who uploaded it.",
    )
    created_at: datetime
    indexed_at: datetime | None = None

    @classmethod
    def of(cls, view: ingest.DocumentView) -> DocumentOut:
        return cls(
            id=view.id,
            title=view.title,
            mime=view.mime,
            status=view.status,
            chunk_count=view.chunk_count,
            embedded_count=view.embedded_count,
            failure_reason=view.failure_reason,
            created_at=view.created_at,
            indexed_at=view.indexed_at,
        )


class PassageOut(BaseModel):
    """One retrieved passage, with what it takes to attribute it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    source: str = Field(description="Document, heading trail and position, as one line.")
    text: str
    found_by: str = Field(description="vector | lexical | both")


class SearchOut(BaseModel):
    """What a search found, and how much of the search ran (**B-073**).

    The envelope exists for the second field. A person looking at an empty
    result needs to know whether their documents do not cover the question or
    whether the half of the search that reads meaning was skipped, and a bare
    list of passages cannot tell them.
    """

    passages: list[PassageOut]
    arms: list[str] = Field(description="Which arms ran: vector, lexical, or both.")
    degraded: str | None = Field(
        default=None,
        description="Why the search by meaning did not run, when it did not.",
    )


@router.post(
    "/orgs/{org_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document and index it",
)
async def upload_document(
    org_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="md, txt, or a PDF with a text layer")],
    title: Annotated[str | None, Form(description="Defaults to the file's name")] = None,
    context: RequestContext = Depends(require_contributor),
) -> DocumentOut:
    payload = await file.read()
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
        )

    view = await ingest.ingest_document(
        org_id=context.org_id,
        title=title or file.filename or "Untitled",
        payload=payload,
        # The browser's guess, which `extract` treats as a hint rather than an authority.
        mime=file.content_type or "application/octet-stream",
        filename=file.filename,
        store=document_store(),
        embedder=document_embedder(),
        actor_user_id=context.user_id,
    )
    # 201 even for a failed ingest, and deliberately.
    return DocumentOut.of(view)


@router.get(
    "/orgs/{org_id}/documents",
    response_model=list[DocumentOut],
    summary="Every document this organization has",
)
async def list_documents(
    org_id: uuid.UUID,
    context: RequestContext = Depends(require_member),
) -> list[DocumentOut]:
    return [DocumentOut.of(view) for view in await ingest.list_documents(org_id=context.org_id)]


@router.post(
    "/orgs/{org_id}/documents/{document_id}/reindex",
    response_model=DocumentOut,
    summary="Chunk and embed a document again from its original bytes",
)
async def reindex(
    org_id: uuid.UUID,
    document_id: DocumentId,
    context: RequestContext = Depends(require_contributor),
) -> DocumentOut:
    try:
        view = await ingest.reindex_document(
            org_id=context.org_id,
            document_id=document_id,
            store=document_store(),
            # This is also the backfill (B-018's shape, applied to documents).
            embedder=document_embedder(),
            actor_user_id=context.user_id,
        )
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document") from None
    return DocumentOut.of(view)


@router.delete(
    "/orgs/{org_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a document and everything retrieved from it",
)
async def remove_document(
    org_id: uuid.UUID,
    document_id: DocumentId,
    context: RequestContext = Depends(require_contributor),
) -> None:
    async with org_session(context.org_id) as session:
        # Read first, so a document belonging to another organization is a 404 rather than a...
        found = (
            await session.execute(
                select(KnowledgeDocument.id).where(KnowledgeDocument.id == document_id)
            )
        ).scalar_one_or_none()
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document")
        # The chunks go with it, by the foreign key rather than by this module remembering.
        await session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id))


@router.get(
    "/orgs/{org_id}/documents/search",
    response_model=SearchOut,
    summary="Search the organization's documents",
)
async def search(
    org_id: uuid.UUID,
    q: Annotated[str, Query(min_length=1, max_length=400)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    context: RequestContext = Depends(require_member),
) -> SearchOut:
    """The same retrieval the agent uses, for a person who wants to see it."""
    found = await search_knowledge(
        org_id=context.org_id,
        query=q,
        limit=limit,
        embedder=document_embedder(),
        actor_user_id=context.user_id,
    )
    return SearchOut(
        passages=[
            PassageOut(
                chunk_id=passage.chunk_id,
                document_id=passage.document_id,
                document_title=passage.document_title,
                source=passage.citation,
                text=passage.text,
                found_by=passage.found_by,
            )
            for passage in found.passages
        ],
        arms=list(found.arms),
        degraded=found.degraded,
    )


@router.get(
    "/orgs/{org_id}/documents/supported-types",
    response_model=list[str],
    summary="What can be uploaded",
)
async def supported_types(
    org_id: uuid.UUID,
    context: RequestContext = Depends(require_member),
) -> list[str]:
    """So the upload control can say what it accepts rather than guessing."""
    return list(SUPPORTED_MIME)
