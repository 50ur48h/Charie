"""Ingest and retrieval, against a real database (plan WP10.1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine

from charie.knowledge.ingest import DocumentView, ingest_document, reindex_document
from charie.knowledge.retrieve import Passage, search_knowledge
from charie.knowledge.store import LocalDocumentStore
from conftest import DIMENSIONS, StubEmbedder, TwoOrgs, unit

POLICY = b"""\
# Revenue policy

Net revenue is the value of completed orders.

## Exclusions

Cancelled and refunded orders are excluded from every revenue figure.
"""

RECIPES = b"""\
# Kitchen handbook

## Dough

Prove the dough for twelve hours before shaping it.
"""


async def _passages(**kwargs: object) -> list[Passage]:
    """Just the passages, for the tests that are about what was found."""
    found = await search_knowledge(**kwargs)  # pyright: ignore[reportArgumentType]
    return list(found.passages)


async def _ingest(
    org_id: uuid.UUID,
    store: LocalDocumentStore,
    payload: bytes,
    title: str,
    embedder: StubEmbedder | None = None,
) -> DocumentView:
    return await ingest_document(
        embedder=embedder,
        org_id=org_id,
        title=title,
        payload=payload,
        mime="text/markdown",
        store=store,
    )


# --- The isolation proof ---


@pytest.mark.rls_proof
async def test_two_organizations_asking_the_same_question_get_zero_cross_hits(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """The test the plan names."""
    embedder = StubEmbedder(vector_for={"revenue": unit(0), "dough": unit(1)})

    await _ingest(orgs.a, store, POLICY, "Alpha revenue policy", embedder=embedder)
    await _ingest(orgs.b, store, POLICY, "Beta revenue policy", embedder=embedder)

    a_hits = await _passages(org_id=orgs.a, query="revenue", embedder=embedder)
    b_hits = await _passages(org_id=orgs.b, query="revenue", embedder=embedder)

    assert a_hits, "the organization's own document was not found"
    assert b_hits, "the organization's own document was not found"

    a_chunks = {hit.chunk_id for hit in a_hits}
    b_chunks = {hit.chunk_id for hit in b_hits}
    assert a_chunks.isdisjoint(b_chunks), "a chunk was returned to both organizations"
    assert {hit.document_title for hit in a_hits} == {"Alpha revenue policy"}
    assert {hit.document_title for hit in b_hits} == {"Beta revenue policy"}


@pytest.mark.rls_proof
async def test_an_organization_with_no_documents_finds_nothing(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """The sharper half of isolation."""
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})
    await _ingest(orgs.a, store, POLICY, "Alpha revenue policy", embedder=embedder)

    assert await _passages(org_id=orgs.b, query="revenue", embedder=embedder) == []


@pytest.mark.rls_proof
async def test_the_rows_themselves_are_scoped_not_only_the_query(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, app_database: URL
) -> None:
    """Reads the tables directly through the application role."""
    await _ingest(orgs.a, store, POLICY, "Alpha revenue policy")

    engine = create_async_engine(app_database)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": str(orgs.b)}
            )
            documents = (
                await connection.execute(text("SELECT count(*) FROM knowledge_documents"))
            ).scalar_one()
            chunks = (
                await connection.execute(text("SELECT count(*) FROM knowledge_chunks"))
            ).scalar_one()
    finally:
        await engine.dispose()

    assert documents == 0, "another organization's documents were visible"
    assert chunks == 0, "another organization's chunks were visible"


# --- What ingest leaves behind ---


async def test_a_document_becomes_searchable_and_says_how_much_of_it_is(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})

    view = await _ingest(orgs.a, store, POLICY, "Revenue policy", embedder=embedder)

    assert view.status == "indexed"
    assert view.chunk_count >= 2
    assert view.embedded_count == view.chunk_count
    assert view.failure_reason is None


async def test_text_is_searchable_before_it_is_embedded(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """The whole reason `embedding` is nullable."""
    view = await _ingest(orgs.a, store, POLICY, "Revenue policy", embedder=None)

    hits = await _passages(org_id=orgs.a, query="cancelled orders")

    assert view.status == "indexed"
    assert view.embedded_count == 0
    assert hits, "unembedded chunks were not findable lexically"
    assert all(hit.found_by == "lexical" for hit in hits)


async def test_an_embedding_failure_keeps_the_text_and_says_what_happened(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """A partial success recorded as a failure with the chunks intact."""
    from charie.knowledge.embeddings import EmbeddingError

    embedder = StubEmbedder(fail_with=EmbeddingError("rate limited", retryable=True))

    view = await _ingest(orgs.a, store, POLICY, "Revenue policy", embedder=embedder)

    assert view.status == "failed"
    assert view.failure_reason is not None
    assert "not embedded" in view.failure_reason
    assert view.chunk_count > 0, "the text was thrown away"
    assert await _passages(org_id=orgs.a, query="cancelled orders"), (
        "the stored text should still be findable"
    )


async def test_a_file_with_no_readable_text_fails_with_a_reason_naming_ocr(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """The failure that otherwise looks exactly like a successful upload of nothing."""
    view = await _ingest(orgs.a, store, b"   \n\n  ", "Scanned handbook")

    assert view.status == "failed"
    assert view.failure_reason is not None
    assert "OCR" in view.failure_reason


async def test_reindexing_replaces_the_chunks_rather_than_appending(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, app_database: URL
) -> None:
    """`seq` is unique per document, so appending would collide."""
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})
    view = await _ingest(orgs.a, store, POLICY, "Revenue policy", embedder=embedder)
    before = view.chunk_count

    again = await reindex_document(
        org_id=orgs.a, document_id=view.id, store=store, embedder=embedder
    )

    assert again.status == "indexed"
    assert again.chunk_count == before, "the chunk count changed on an unchanged document"

    engine = create_async_engine(app_database)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": str(orgs.a)}
            )
            total = (
                await connection.execute(
                    text("SELECT count(*) FROM knowledge_chunks WHERE document_id = :d"),
                    {"d": view.id},
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert total == before, "re-indexing appended instead of replacing"


# --- What retrieval actually returns ---


async def test_a_passage_can_name_where_it_came_from(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """Provenance is what makes retrieved text safe to show at all (5.5)."""
    await _ingest(orgs.a, store, POLICY, "Revenue policy")

    hits = await _passages(org_id=orgs.a, query="cancelled refunded orders")

    assert hits
    best = hits[0]
    assert best.document_title == "Revenue policy"
    assert "Revenue policy" in best.citation
    assert best.headings, "the heading trail was lost between ingest and retrieval"


async def test_the_vector_arm_finds_what_the_words_do_not(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """B-018's whole argument, in one test."""
    embedder = StubEmbedder(vector_for={"cancelled": unit(0), "takings": unit(0)})
    await _ingest(orgs.a, store, POLICY, "Revenue policy", embedder=embedder)

    hits = await _passages(org_id=orgs.a, query="takings", embedder=embedder)

    assert hits, "nothing was found for a query sharing no words with the document"
    assert any(hit.found_by in {"vector", "both"} for hit in hits)


async def test_a_query_nobody_can_answer_returns_nothing_rather_than_anything(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """With no embedder there is no vector arm, so a query matching no word must come back empty."""
    await _ingest(orgs.a, store, RECIPES, "Kitchen handbook")

    assert await _passages(org_id=orgs.a, query="quarterly depreciation") == []


async def test_an_empty_query_costs_no_provider_call(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    embedder = StubEmbedder()

    assert await _passages(org_id=orgs.a, query="   ", embedder=embedder) == []
    assert embedder.calls == 0


async def test_one_document_cannot_fill_the_whole_result(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """A long document otherwise wins every slot on term frequency alone."""
    sections = b"\n\n".join(
        f"## Section {n}\n\nCancelled orders are excluded from revenue here too.".encode()
        for n in range(8)
    )
    await _ingest(orgs.a, store, b"# Long policy\n\n" + sections, "Long policy")
    await _ingest(orgs.a, store, POLICY, "Short policy")

    hits = await _passages(org_id=orgs.a, query="cancelled orders excluded", limit=5)

    from collections import Counter

    per_document = Counter(hit.document_id for hit in hits)
    assert max(per_document.values()) <= 2, "one document filled the result"


async def test_a_search_can_be_narrowed_to_one_document(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    await _ingest(orgs.a, store, POLICY, "Revenue policy")
    handbook = await _ingest(orgs.a, store, RECIPES, "Kitchen handbook")

    hits = await _passages(org_id=orgs.a, query="dough orders revenue", document_id=handbook.id)

    assert hits
    assert {hit.document_id for hit in hits} == {handbook.id}


async def test_the_stub_never_produces_a_vector_of_the_wrong_width(
    orgs: TwoOrgs, store: LocalDocumentStore
) -> None:
    """Guards the fixture rather than the product."""
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})

    batch = await embedder.embed(["revenue"])

    assert len(batch.vectors[0]) == DIMENSIONS
