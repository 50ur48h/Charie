"""In the one-command demo, whoever signs in lands in the demo organization."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from charie.auth.jwt_validator import TokenValidator
from charie.auth.principal import Principal, TokenError
from charie.config import Settings
from charie.db import engine as engine_module
from charie.db.models import User
from charie.main import create_app
from charie.orgs import service as orgs_service
from charie.orgs.service import demo_org_id
from charie.tenancy import session as session_module

DEMO = "Charie demo"


class _SubjectAsToken(TokenValidator):
    def __init__(self) -> None:
        pass

    async def validate(self, token: str) -> Principal:
        if not token:
            raise TokenError("malformed", "nope")
        return Principal(subject=token, email=f"{token}@example.com", name=token.title())


async def _me(app: FastAPI, who: str) -> dict[str, Any]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/v1/me", headers={"Authorization": f"Bearer {who}"})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
async def make_app(
    app_database: URL, migrated_database: URL, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Callable[..., FastAPI]]:
    owner = create_async_engine(migrated_database)
    app_engine = create_async_engine(app_database)
    monkeypatch.setattr(engine_module, "get_engine", lambda: owner)
    monkeypatch.setattr(
        session_module,
        "_session_factory",
        lambda: async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False),
    )
    async with owner.begin() as connection:
        await connection.execute(
            text("INSERT INTO organizations (id, name) VALUES (:i, :n)"),
            {"i": demo_org_id(DEMO), "n": DEMO},
        )

    def build(**overrides: Any) -> FastAPI:
        values: dict[str, Any] = {"auth_mode": "dev", "env": "ci", "build_env": "dev", **overrides}
        app = create_app(settings=Settings(_env_file=None, **values))  # pyright: ignore[reportCallIssue]
        app.state.token_validator = _SubjectAsToken()
        return app

    try:
        yield build
    finally:
        await owner.dispose()
        await app_engine.dispose()


async def test_anyone_who_signs_in_joins_the_demo_organization(
    make_app: Callable[..., FastAPI],
) -> None:
    app = make_app(demo_org=DEMO)

    me = await _me(app, "sourabh")

    assert [(m["org_name"], m["role"]) for m in me["memberships"]] == [(DEMO, "admin")]
    # Signing in again does not add a second membership.
    assert len((await _me(app, "sourabh"))["memberships"]) == 1


async def test_without_a_demo_organization_nobody_is_joined_to_anything(
    make_app: Callable[..., FastAPI],
) -> None:
    me = await _me(make_app(), "no-demo-user")

    assert me["memberships"] == []


async def test_a_production_environment_never_auto_joins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(org_id: object) -> object:
        raise AssertionError("a production process looked for the demo organization")

    monkeypatch.setattr(orgs_service, "org_session", refuse)
    settings = Settings(_env_file=None, env="prod", auth_mode="entra", demo_org=DEMO)  # pyright: ignore[reportCallIssue]

    await orgs_service.join_demo_org(User(external_subject="prod-user"), settings)
