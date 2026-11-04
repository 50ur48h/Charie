"""Card search by meaning, not only by wording (B-018)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence

import pytest
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from charie.catalog import cards, discovery, profiler, search
from charie.datasources import service as datasources
from charie.db import engine as engine_module
from charie.knowledge.embeddings import EmbeddingBatch
from charie.llm.base import Usage
from charie.secrets.local import LocalSecretsProvider
from charie.tenancy import session as session_module
from customer_db import CustomerDatabase
from llm_fixture import build_settings

DIMENSIONS = 1536


class StubEmbedder:
    """Vectors the test chooses, and a count of what it was asked to embed."""

    def __init__(self, vector_for: dict[str, list[float]] | None = None) -> None:
        self.vector_for = vector_for or {}
        self.seen: list[str] = []
        self.calls = 0
        self.fail_with: Exception | None = None
        self.is_stub = True
        self.model = "stub-embedding"

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        self.calls += 1
        self.seen.extend(texts)
        if self.fail_with is not None:
            raise self.fail_with
        vectors: list[tuple[float, ...]] = []
        for item in texts:
            chosen = next(
                (
                    vector
                    for needle, vector in self.vector_for.items()
                    if needle.lower() in item.lower()
                ),
                None,
            )
            vectors.append(tuple(chosen if chosen is not None else [0.0] * DIMENSIONS))
        return EmbeddingBatch(
            vectors=tuple(vectors),
            usage=Usage(input_tokens=len(texts), output_tokens=0),
            model=self.model,
        )

    async def aclose(self) -> None:
        return None


def unit(index: int) -> list[float]:
    """A basis vector: 1.0 in one position and 0.0 elsewhere."""
    vector = [0.0] * DIMENSIONS
    vector[index] = 1.0
    return vector


@pytest.fixture
async def platform(
    app_database: URL,
    migrated_database: URL,
    secrets_provider: LocalSecretsProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[URL]:
    owner = create_async_engine(migrated_database)
    app_engine = create_async_engine(app_database)
    monkeypatch.setattr(engine_module, "get_engine", lambda: owner)
    monkeypatch.setattr(
        session_module,
        "_session_factory",
        lambda: async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False),
    )
    try:
        yield app_database
    finally:
        await owner.dispose()
        await app_engine.dispose()


async def _catalogued(
    migrated_database: URL,
    customer: CustomerDatabase,
    *,
    embedder: StubEmbedder | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """An organization with one discovered, carded data source."""
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    engine = create_async_engine(migrated_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, true)"), {"org": str(org_id)}
            )
            await connection.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, 'Vectors')"), {"id": org_id}
            )
            await connection.execute(
                text("INSERT INTO users (id, external_subject, email) VALUES (:i, :s, :e)"),
                {"i": user_id, "s": f"sub-{user_id}", "e": "owner@example.com"},
            )
            await connection.execute(
                text(
                    "INSERT INTO org_memberships (org_id, user_id, role) VALUES (:o, :u, 'admin')"
                ),
                {"o": org_id, "u": user_id},
            )
    finally:
        await engine.dispose()

    view = await datasources.create_data_source(
        org_id=org_id,
        actor_user_id=user_id,
        name="Customer",
        engine="pg",
        host=customer.host,
        port=customer.port,
        database=customer.database,
        username=customer.reader_username,
        password=customer.reader_password,
        tls_mode="prefer",
    )
    await datasources.test_data_source(org_id=org_id, actor_user_id=user_id, data_source_id=view.id)
    await discovery.discover(
        org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=embedder
    )
    # Profiled, like `test_cards_and_search.py`'s fixture.
    await profiler.profile(
        org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=embedder
    )
    return org_id, view.id


async def _embedded(url: URL, org_id: uuid.UUID) -> dict[str, bool]:
    """Which cards carry a vector, by table name, read as the app role would."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": str(org_id)}
            )
            rows = (
                await connection.execute(
                    text(
                        "SELECT t.table_name, t.embedding IS NOT NULL AS embedded, t.flags "
                        "FROM catalog_tables t "
                        "JOIN catalog_snapshots s ON s.id = t.snapshot_id "
                        "WHERE s.status = 'active'"
                    )
                )
            ).mappings()
            return {row["table_name"]: bool(row["embedded"]) for row in rows}
    finally:
        await engine.dispose()


# --- The backfill ---


async def test_discovering_a_catalog_embeds_its_cards(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """One pass, at the moment the cards are written."""
    embedder = StubEmbedder()

    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=embedder)

    embedded = await _embedded(platform, org_id)
    assert embedded, "the catalog has no cards at all"
    assert all(embedded.values()), f"some cards were left unembedded: {embedded}"


async def test_a_deployment_with_no_embedder_still_gets_its_cards(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """The absence of an embedding model is a supported state."""
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database)

    embedded = await _embedded(platform, org_id)
    assert embedded and not any(embedded.values())
    assert await search.search_cards(org_id, "trading name"), "lexical search stopped working"


async def test_the_backfill_is_idempotent(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """What makes it a backfill rather than a rebuild."""
    embedder = StubEmbedder()
    org_id, source_id = await _catalogued(
        migrated_database, isolated_customer_database, embedder=embedder
    )
    after_first = embedder.calls

    written = await cards.embed_cards(
        org_id, source_id, embedder=embedder, settings=build_settings()
    )

    assert written == 0, "the backfill re-embedded cards that already had vectors"
    assert embedder.calls == after_first, "the provider was called with nothing to do"


async def test_a_provider_failure_leaves_the_cards_lexically_searchable(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """The cards were already written."""
    from charie.knowledge.embeddings import EmbeddingError

    broken = StubEmbedder()
    broken.fail_with = EmbeddingError("rate limited", retryable=True)

    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=broken)

    embedded = await _embedded(platform, org_id)
    assert embedded, "the refresh failed outright instead of degrading"
    assert not any(embedded.values())
    assert await search.search_cards(org_id, "trading name")


async def test_an_unchanged_card_keeps_the_vector_it_already_paid_for(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """D-012's rule — a refresh that finds no change writes nothing."""
    embedder = StubEmbedder()
    org_id, source_id = await _catalogued(
        migrated_database, isolated_customer_database, embedder=embedder
    )
    after_first = embedder.calls

    await cards.refresh_cards(org_id, source_id)
    await cards.embed_cards(org_id, source_id, embedder=embedder, settings=build_settings())

    assert embedder.calls == after_first, "an unchanged card was re-embedded"
    assert all((await _embedded(platform, org_id)).values())


# --- What the vector arm buys ---


async def test_a_card_is_found_by_a_question_that_shares_no_word_with_it(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """B-018 in one test, and golden eval #14 in miniature."""
    embedder = StubEmbedder(vector_for={"shops (public.shops)": unit(3), "outlets we run": unit(3)})
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=embedder)
    question = "outlets we run"

    lexical = await search.search_cards(org_id, question)
    hybrid = await search.search_cards(
        org_id, question, embedder=embedder, settings=build_settings()
    )

    assert lexical == [], "the question was findable by wording, so this proves nothing"
    assert hybrid, "the vector arm found nothing the lexical arm had missed"
    assert hybrid[0].table_name == "shops"
    assert hybrid[0].found_by == "vector"


async def test_a_card_both_arms_agree_on_outranks_one_either_found_alone(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """What Reciprocal Rank Fusion is for."""
    embedder = StubEmbedder(vector_for={"shops (public.shops)": unit(3), "trading name": unit(3)})
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=embedder)

    hits = await search.search_cards(
        org_id, "trading name", embedder=embedder, settings=build_settings()
    )

    assert hits
    assert hits[0].table_name == "shops"
    assert hits[0].found_by == "both"
    assert all(hit.rank <= hits[0].rank for hit in hits)


async def test_without_an_embedder_the_ranking_is_the_one_it_always_was(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """A regression guard rather than a feature."""
    embedder = StubEmbedder()
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=embedder)

    hits = await search.search_cards(org_id, "How many shops opened in 2021?")

    assert [hit.table_name for hit in hits][:1] == ["shops"]
    assert all(hit.found_by == "lexical" for hit in hits)


async def test_the_search_says_which_arm_found_each_card(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """`found_by` reaches `context_selected`."""
    embedder = StubEmbedder(
        vector_for={"regions (public.regions)": unit(7), "areas of the country": unit(7)}
    )
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=embedder)

    hits = await search.search_cards(
        org_id, "areas of the country", embedder=embedder, settings=build_settings()
    )

    assert hits
    assert {hit.found_by for hit in hits} <= {"vector", "lexical", "both"}
    assert any(hit.found_by == "vector" for hit in hits)


async def test_a_failed_query_embedding_falls_back_to_wording_rather_than_failing(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """This is the context stage of every run."""
    from charie.knowledge.embeddings import EmbeddingError

    working = StubEmbedder()
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=working)
    broken = StubEmbedder()
    broken.fail_with = EmbeddingError("rate limited", retryable=True)

    hits = await search.search_cards(
        org_id, "trading name", embedder=broken, settings=build_settings()
    )

    assert hits, "a failed query embedding took the whole search down with it"
    assert all(hit.found_by == "lexical" for hit in hits)


async def test_a_loose_question_is_answered_by_meaning_and_not_by_word_overlap(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """B-159. The OR fallback does not vote once there is a vector arm."""
    # Real vectors rather than the stub's zeros: a zero vector has no cosine distance.
    embedder = StubEmbedder(vector_for={"1999": unit(1), "region": unit(1)})
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database, embedder=embedder)

    # "1999" appears in no card, so `websearch_to_tsquery`'s AND cannot match and the fallback...
    hits = await search.search_cards(
        org_id,
        "How did our shops and regions look in 1999?",
        embedder=embedder,
        settings=build_settings(),
    )

    assert hits, "the vector arm must still answer a question the wording cannot"
    assert all(hit.found_by == "vector" for hit in hits), (
        f"the OR fallback voted anyway: {[(hit.table_name, hit.found_by) for hit in hits]}"
    )


async def test_without_an_embedder_the_or_fallback_still_answers(
    platform: URL, migrated_database: URL, isolated_customer_database: CustomerDatabase
) -> None:
    """The other half of B-159, and the half that must not regress."""
    org_id, _ = await _catalogued(migrated_database, isolated_customer_database)

    hits = await search.search_cards(org_id, "How did our shops and regions look in 1999?")

    assert hits, "with no vector arm the fallback is the only thing that can answer"
    assert all(hit.found_by == "lexical" for hit in hits)
