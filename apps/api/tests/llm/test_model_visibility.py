"""Every model call in a run is visible in its trace, and a picked model serves every role."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from charie.config import Settings
from charie.db import engine as engine_module
from charie.llm import registry, service
from charie.llm.base import LLMError, Message
from charie.llm.fake import FakeLLM
from charie.tenancy import session as session_module
from llm_fixture import build_settings, seed_run

QUESTION = [Message(role="system", content="rules"), Message(role="user", content="ask")]
SPARK = "muse-spark-1.3"
WONDER = "muse-wonder-1.0"


@pytest.fixture
async def platform(
    app_database: URL, migrated_database: URL, monkeypatch: pytest.MonkeyPatch
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


async def _org(migrated_database: URL) -> uuid.UUID:
    org_id = uuid.uuid4()
    engine = create_async_engine(migrated_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, 'Visible')"),
                {"id": org_id},
            )
    finally:
        await engine.dispose()
    return org_id


async def _events(url: URL, org_id: uuid.UUID) -> list[dict[str, object]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": str(org_id)}
            )
            rows = await connection.execute(
                text("SELECT type, payload FROM agent_events ORDER BY seq")
            )
            return [dict(row) for row in rows.mappings().all()]
    finally:
        await engine.dispose()


async def test_a_call_in_a_run_names_its_model_in_the_trace(
    platform: URL, migrated_database: URL, fake_llm: FakeLLM
) -> None:
    org_id = await _org(migrated_database)
    run_id = await seed_run(migrated_database, org_id)
    fake_llm.script("ok")

    await service.complete(
        role="plan", org_id=org_id, messages=QUESTION, run_id=run_id, settings=build_settings()
    )

    (event,) = await _events(platform, org_id)
    assert event["type"] == "model_called"
    payload = event["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "fake-strong"
    assert payload["role"] == "plan"
    assert payload["status"] == "ok"
    assert isinstance(payload["latency_ms"], int)


async def test_a_failed_call_is_in_the_trace_too(
    platform: URL, migrated_database: URL, fake_llm: FakeLLM
) -> None:
    org_id = await _org(migrated_database)
    run_id = await seed_run(migrated_database, org_id)
    fake_llm.script(raises=LLMError("the provider refused the request", retryable=False))

    with pytest.raises(LLMError):
        await service.complete(
            role="sql", org_id=org_id, messages=QUESTION, run_id=run_id, settings=build_settings()
        )

    (event,) = await _events(platform, org_id)
    payload = event["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "error"
    assert payload["error"] == "the provider refused the request"


async def test_a_call_outside_a_run_leaves_no_trace(
    platform: URL, migrated_database: URL, fake_llm: FakeLLM
) -> None:
    org_id = await _org(migrated_database)
    fake_llm.script("ok")

    await service.complete(role="plan", org_id=org_id, messages=QUESTION, settings=build_settings())

    assert await _events(platform, org_id) == []


def _meta_settings() -> Settings:
    return build_settings(
        llm_providers=("meta",),
        llm_models={"meta": {"small": SPARK, "mid": SPARK, "strong": SPARK}},
        llm_selectable_models=(WONDER, SPARK),
    )


def test_a_picked_model_serves_every_role_and_only_inside_its_run() -> None:
    settings = _meta_settings()

    with registry.use_model(WONDER):
        chains = [
            registry.resolve("intake", settings),
            registry.resolve("plan", settings),
            registry.resolve("compose", settings),
        ]
    after = registry.resolve("plan", settings)

    assert all(len(chain) == 1 for chain in chains)
    assert {choice.model for chain in chains for choice in chain} == {WONDER}
    assert {choice.provider for chain in chains for choice in chain} == {"meta"}
    assert [choice.model for choice in after] == [SPARK]


def test_the_default_comes_first_and_nothing_is_offered_twice() -> None:
    assert registry.selectable_models(_meta_settings()) == (SPARK, WONDER)


def test_with_no_list_the_configured_models_are_offered() -> None:
    settings = build_settings(
        llm_providers=("meta",),
        llm_models={"meta": {"small": SPARK, "mid": SPARK, "strong": WONDER}},
    )

    assert registry.selectable_models(settings) == (WONDER, SPARK)
