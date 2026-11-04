"""Embedding spend inside a run, and the ceiling that bounds it (B-073)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine

from charie.agent.tools.base import ToolContext
from charie.agent.tools.knowledge import SEARCH_KNOWLEDGE, SearchKnowledgeIn, SearchKnowledgeOut
from charie.knowledge.ingest import ingest_document
from charie.knowledge.retrieve import search_knowledge
from charie.knowledge.store import LocalDocumentStore
from charie.llm import meter
from charie.llm.base import Usage
from conftest import StubEmbedder, TwoOrgs, unit
from llm_fixture import build_settings, seed_run

POLICY = b"""\
# Revenue policy

## Net revenue

Net revenue excludes cancelled and refunded orders.
"""

#: The stub's model id, priced so a ceiling can count it.
PRICES = {
    "stub-embedding": {"input": 1.0, "output": 0.0},
    "fake-strong": {"input": 10.0, "output": 30.0},
}


async def _ledger(url: URL, org_id: uuid.UUID, run_id: uuid.UUID | None) -> list[dict[str, object]]:
    """The organization's embedding rows, read as the application role would."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": str(org_id)}
            )
            rows = (
                await connection.execute(
                    text(
                        "SELECT run_id, role, tier, model, input_tokens, cost_usd, status "
                        "FROM usage_ledger WHERE role = 'embed' ORDER BY created_at"
                    )
                )
            ).mappings()
            return [dict(row) for row in rows]
    finally:
        await engine.dispose()


async def _upload(
    org_id: uuid.UUID, store: LocalDocumentStore, embedder: StubEmbedder | None
) -> None:
    await ingest_document(
        org_id=org_id,
        title="Revenue policy",
        payload=POLICY,
        mime="text/markdown",
        store=store,
        embedder=embedder,
        settings=build_settings(llm_prices=PRICES),
    )


# --- The spend lands on the run ---


async def test_a_query_embedding_is_charged_to_the_run_that_asked(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, migrated_database: URL
) -> None:
    """The property the ceiling is built on."""
    run_id = await seed_run(migrated_database, orgs.a)
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})
    await _upload(orgs.a, store, None)

    await search_knowledge(
        org_id=orgs.a,
        query="revenue",
        embedder=embedder,
        run_id=run_id,
        actor_user_id=orgs.a_user,
        settings=build_settings(llm_prices=PRICES),
    )

    rows = await _ledger(migrated_database, orgs.a, run_id)
    assert len(rows) == 1, "the query embedding did not leave exactly one ledger row"
    charged = rows[0]
    assert charged["run_id"] == run_id
    # Its own role and tier (revision 0017), never `small`.
    assert charged["role"] == "embed"
    assert charged["tier"] == "embed"
    assert charged["model"] == "stub-embedding"
    assert charged["status"] == "ok"
    assert charged["cost_usd"] == Decimal("0.000001"), "a priced embedding recorded no cost"


async def test_ingest_spend_is_recorded_even_though_no_run_asked_for_it(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, migrated_database: URL
) -> None:
    """An upload is not a run and has nothing to accumulate against."""
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})

    await _upload(orgs.a, store, embedder)

    rows = await _ledger(migrated_database, orgs.a, None)
    assert rows, "embedding a document left no ledger row at all"
    assert all(row["run_id"] is None for row in rows)


# --- The ceiling, and what it does to a search ---


async def test_a_run_at_its_ceiling_still_gets_a_lexical_answer_and_is_told_why(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, migrated_database: URL
) -> None:
    """The trade this design makes, asserted rather than described."""
    run_id = await seed_run(migrated_database, orgs.a)
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})
    await _upload(orgs.a, store, embedder)
    # A prior, priced chat call that used the whole ceiling.
    await meter.record(
        org_id=orgs.a,
        role="plan",
        tier="strong",
        provider="fake",
        model="fake-strong",
        usage=Usage(input_tokens=1_000_000, output_tokens=0),  # $10.00
        latency_ms=1,
        run_id=run_id,
        settings=build_settings(llm_prices=PRICES),
    )
    before = embedder.calls

    found = await search_knowledge(
        org_id=orgs.a,
        query="cancelled refunded orders",
        embedder=embedder,
        run_id=run_id,
        settings=build_settings(llm_prices=PRICES, llm_run_cost_limit_usd=1.0),
    )

    assert embedder.calls == before, "the ceiling was checked after the spend, not before"
    assert found.arms == ("lexical",)
    assert found.degraded is not None
    assert "spending ceiling" in found.degraded
    assert found.passages, "the lexical arm was taken away along with the vector arm"


async def test_an_unpriced_embedding_model_under_a_ceiling_is_refused_the_same_way(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, migrated_database: URL
) -> None:
    """D-019's rule, arriving through the new door."""
    run_id = await seed_run(migrated_database, orgs.a)
    embedder = StubEmbedder(vector_for={"revenue": unit(0)})
    await _upload(orgs.a, store, embedder)

    found = await search_knowledge(
        org_id=orgs.a,
        query="cancelled refunded orders",
        embedder=embedder,
        run_id=run_id,
        settings=build_settings(llm_prices={}, llm_run_cost_limit_usd=1.0),
    )

    assert found.arms == ("lexical",)
    assert found.degraded is not None
    assert found.passages


async def test_a_provider_failure_degrades_the_search_rather_than_failing_it(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, migrated_database: URL
) -> None:
    """A rate limit is not a reason to answer nothing."""
    from charie.knowledge.embeddings import EmbeddingError

    run_id = await seed_run(migrated_database, orgs.a)
    await _upload(orgs.a, store, None)
    broken = StubEmbedder(fail_with=EmbeddingError("rate limited", retryable=True))

    found = await search_knowledge(
        org_id=orgs.a,
        query="cancelled refunded orders",
        embedder=broken,
        run_id=run_id,
        settings=build_settings(llm_prices=PRICES),
    )

    assert found.arms == ("lexical",)
    assert found.degraded is not None
    assert "could not be run" in found.degraded
    assert found.passages
    # The failed attempt is on the ledger, as `llm/service.py` records a failed completion.
    rows = await _ledger(migrated_database, orgs.a, run_id)
    assert [row["status"] for row in rows] == ["error"]
    assert rows[0]["run_id"] == run_id


# --- What the model is told ---


async def _call(context: ToolContext, query: str) -> SearchKnowledgeOut:
    result = await SEARCH_KNOWLEDGE.handler(context, SearchKnowledgeIn(query=query))
    assert isinstance(result, SearchKnowledgeOut)
    return result


async def test_the_tool_searches_by_meaning_when_the_run_has_an_embedder(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, migrated_database: URL
) -> None:
    """B-073's practical cost, closed."""
    run_id = await seed_run(migrated_database, orgs.a)
    embedder = StubEmbedder(vector_for={"cancelled": unit(0), "takings": unit(0)})
    await _upload(orgs.a, store, embedder)
    context = ToolContext(
        org_id=orgs.a,
        run_id=run_id,
        role="reader",
        embedder=embedder,
        settings=build_settings(llm_prices=PRICES),
    )

    result = await _call(context, "takings")

    assert result.passages, "a query sharing no word with the document found nothing"
    assert any(passage.found_by in {"vector", "both"} for passage in result.passages)
    assert result.note == "", "a search that ran in full should not report a degradation"


async def test_a_degraded_search_that_finds_nothing_does_not_say_nothing_is_written_down(
    orgs: TwoOrgs, store: LocalDocumentStore, wired: URL, migrated_database: URL
) -> None:
    """The distinction this whole entry turns on."""
    run_id = await seed_run(migrated_database, orgs.a)
    await _upload(orgs.a, store, None)
    context = ToolContext(
        org_id=orgs.a,
        run_id=run_id,
        role="reader",
        embedder=None,
        settings=build_settings(llm_prices=PRICES),
    )

    result = await _call(context, "zzzz nonexistent term")

    assert result.passages == []
    assert "no embedding model configured" in result.note
    assert "do not infer a definition" in result.note
    assert result.note.index("embedding model") < result.note.index("do not infer")
