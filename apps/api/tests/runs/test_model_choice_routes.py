"""Picking the Meta model that answers a question."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from charie.auth.jwt_validator import TokenValidator
from charie.auth.principal import Principal, TokenError
from charie.config import Settings
from charie.db import engine as engine_module
from charie.main import create_app
from charie.tenancy import session as session_module

SPARK = "muse-spark-1.3"
WONDER = "muse-wonder-1.0"


class _SubjectAsToken(TokenValidator):
    def __init__(self) -> None:
        pass

    async def validate(self, token: str) -> Principal:
        if not token:
            raise TokenError("malformed", "nope")
        return Principal(subject=token, email=f"{token}@example.com", name=token.title())


class Api:
    def __init__(self, app: FastAPI) -> None:
        self._app = app

    async def call(
        self, method: str, path: str, who: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        async with AsyncClient(
            transport=ASGITransport(app=self._app), base_url="http://testserver"
        ) as client:
            response = await client.request(
                method, path, headers={"Authorization": f"Bearer {who}"}, json=body
            )
        return response.status_code, response.json()


@pytest.fixture
async def api(
    app_database: URL, migrated_database: URL, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Api]:
    owner = create_async_engine(migrated_database)
    app_engine = create_async_engine(app_database)
    monkeypatch.setattr(engine_module, "get_engine", lambda: owner)
    monkeypatch.setattr(
        session_module,
        "_session_factory",
        lambda: async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False),
    )
    scheduled: list[dict[str, Any]] = []

    async def record(**kwargs: Any) -> None:
        scheduled.append(kwargs)

    # The run itself is not under test here, only what it was scheduled with.
    monkeypatch.setattr("charie.runs.routes.schedule_run", record)
    values: dict[str, Any] = {
        "auth_mode": "dev",
        "env": "ci",
        "build_env": "dev",
        "llm_providers": ("meta",),
        "llm_models": {"meta": {"small": SPARK, "mid": SPARK, "strong": SPARK}},
        "llm_selectable_models": (SPARK, WONDER),
    }
    settings = Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]
    app = create_app(settings=settings)
    app.state.token_validator = _SubjectAsToken()
    app.state.scheduled = scheduled
    try:
        yield Api(app)
    finally:
        await owner.dispose()
        await app_engine.dispose()


async def _conversation(api: Api) -> tuple[str, str]:
    _, org = await api.call("POST", "/v1/orgs", "alice", {"name": "Acme"})
    org_id = str(org["org_id"])
    _, conversation = await api.call("POST", f"/v1/orgs/{org_id}/conversations", "alice", {})
    return org_id, str(conversation["id"])


async def test_the_models_on_offer_are_the_meta_models_default_first(api: Api) -> None:
    org_id, _ = await _conversation(api)

    status, body = await api.call("GET", f"/v1/orgs/{org_id}/models", "alice")

    assert status == 200
    assert body == {
        "default": SPARK,
        "models": [
            {"id": SPARK, "name": "Muse Spark 1.3"},
            {"id": WONDER, "name": "Muse Wonder 1.0"},
        ],
    }


async def test_a_picked_model_is_kept_on_the_run_and_given_to_the_scheduler(api: Api) -> None:
    org_id, conversation_id = await _conversation(api)

    status, accepted = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/conversations/{conversation_id}/messages",
        "alice",
        {"content": "Which outlets grew?", "idempotency_key": "k-1", "model": WONDER},
    )
    assert status == 202, accepted

    _, run = await api.call("GET", f"/v1/orgs/{org_id}/runs/{accepted['run_id']}", "alice")
    assert run["model"] == WONDER
    scheduled = api._app.state.scheduled  # pyright: ignore[reportPrivateUsage]
    assert scheduled[-1]["model"] == WONDER


async def test_a_model_that_is_not_on_offer_is_refused(api: Api) -> None:
    org_id, conversation_id = await _conversation(api)

    status, body = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/conversations/{conversation_id}/messages",
        "alice",
        {"content": "Which outlets grew?", "idempotency_key": "k-2", "model": "gpt-5"},
    )

    assert status == 422
    assert "gpt-5" in body["detail"]


async def test_no_pick_means_the_default(api: Api) -> None:
    org_id, conversation_id = await _conversation(api)

    _, accepted = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/conversations/{conversation_id}/messages",
        "alice",
        {"content": "Which outlets grew?", "idempotency_key": "k-3"},
    )

    _, run = await api.call("GET", f"/v1/orgs/{org_id}/runs/{accepted['run_id']}", "alice")
    assert run["model"] is None
