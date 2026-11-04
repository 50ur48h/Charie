"""Resolving a citation into evidence (architecture 10.2, B-034)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
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
from charie.main import create_app
from charie.tenancy import session as session_module
from charie.tenancy.session import org_session


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
        return response.status_code, (None if response.status_code == 204 else response.json())


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
    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken()
    try:
        yield Api(app)
    finally:
        await owner.dispose()
        await app_engine.dispose()


async def _org(api: Api, name: str = "Acme") -> str:
    _, org = await api.call("POST", "/v1/orgs", "alice", {"name": name})
    return str(org["org_id"])


async def _run(api: Api, org_id: str, who: str = "alice", key: str = "send-1") -> str:
    _, conversation = await api.call("POST", f"/v1/orgs/{org_id}/conversations", who, {})
    _, accepted = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/conversations/{conversation['id']}/messages",
        who,
        {"content": "How many orders were placed in July 2026?", "idempotency_key": key},
    )
    return str(accepted["run_id"])


async def _record_success(org_id: str, run_id: str) -> str:
    """One execution that ran, with the artifact the DAL writes beside it."""
    execution_id = uuid.uuid4()
    async with org_session(uuid.UUID(org_id)) as session:
        await session.execute(
            text(
                "INSERT INTO query_executions (id, org_id, run_id, sql_text, sql_hash, "
                "tables, columns, status, row_count, duration_ms, sensitive_accessed) "
                "VALUES (:i, :o, :r, :sql, 'abc123def456', "
                "'[\"public.orders\"]'::jsonb, '[\"public.orders.id\"]'::jsonb, "
                "'ok', 128, 14, true)"
            ),
            {
                "i": execution_id,
                "o": org_id,
                "r": run_id,
                "sql": 'SELECT COUNT(*) AS "order_count" FROM "public"."orders"',
            },
        )
        await session.execute(
            text(
                "INSERT INTO result_artifacts (id, org_id, query_execution_id, summary, "
                "sample_rows, truncated, expires_at) VALUES (:i, :o, :q, :s, :rows, false, "
                "now() + interval '30 days')"
            ),
            {
                "i": uuid.uuid4(),
                "o": org_id,
                "q": execution_id,
                "s": (
                    '{"columns": ["order_count", "email"], "row_count": 128, '
                    '"truncated": false, "masked_columns": ["email"], "duration_ms": 14}'
                ),
                "rows": '[[128, "k***@e***.com"]]',
            },
        )
    return str(execution_id)


async def _record_refusal(org_id: str, run_id: str) -> str:
    """A statement this service would not send. No artifact — nothing ran."""
    execution_id = uuid.uuid4()
    async with org_session(uuid.UUID(org_id)) as session:
        await session.execute(
            text(
                "INSERT INTO query_executions (id, org_id, run_id, sql_text, sql_hash, "
                "status, violation_code, error) VALUES (:i, :o, :r, :sql, 'deadbeef1234', "
                "'refused', 'unknown_column', :err)"
            ),
            {
                "i": execution_id,
                "o": org_id,
                "r": run_id,
                "sql": "SELECT customer_name FROM orders",
                "err": "Unknown column 'customer_name' on public.orders",
            },
        )
    return str(execution_id)


# --- What a citation resolves to ---


async def test_a_citation_resolves_to_the_query_behind_it(api: Api) -> None:
    org_id = await _org(api)
    run_id = await _run(api, org_id)
    execution_id = await _record_success(org_id, run_id)

    status, evidence = await api.call(
        "GET", f"/v1/orgs/{org_id}/runs/{run_id}/executions/{execution_id}", "alice"
    )

    assert status == 200
    assert evidence["status"] == "ok"
    assert evidence["sql"] == 'SELECT COUNT(*) AS "order_count" FROM "public"."orders"'
    assert evidence["tables"] == ["public.orders"]
    assert evidence["columns"] == ["order_count", "email"]
    assert evidence["row_count"] == 128
    assert evidence["duration_ms"] == 14
    assert evidence["truncated"] is False


async def test_the_rows_a_reader_is_shown_are_the_masked_ones(api: Api) -> None:
    """Masked on the way in (D-013, WP5.2b), so there is nothing else to send."""
    org_id = await _org(api)
    run_id = await _run(api, org_id)
    execution_id = await _record_success(org_id, run_id)

    _, evidence = await api.call(
        "GET", f"/v1/orgs/{org_id}/runs/{run_id}/executions/{execution_id}", "alice"
    )

    assert evidence["masked_columns"] == ["email"]
    assert evidence["sample_rows"] == [[128, "k***@e***.com"]]
    assert evidence["sensitive_accessed"] is True


async def test_a_refused_query_says_what_refused_it(api: Api) -> None:
    """Not an empty result — which would read as "your data has no answer"."""
    org_id = await _org(api)
    run_id = await _run(api, org_id)
    execution_id = await _record_refusal(org_id, run_id)

    status, evidence = await api.call(
        "GET", f"/v1/orgs/{org_id}/runs/{run_id}/executions/{execution_id}", "alice"
    )

    assert status == 200
    assert evidence["status"] == "refused"
    assert evidence["violation_code"] == "unknown_column"
    assert evidence["error"] == "Unknown column 'customer_name' on public.orders"
    assert evidence["sample_rows"] == []
    assert evidence["row_count"] is None


# --- Who may open it ---


async def test_an_execution_from_another_run_is_not_found(api: Api) -> None:
    """Even your own. The run in the path is in the WHERE clause, not decoration."""
    org_id = await _org(api)
    mine, other = await _run(api, org_id), await _run(api, org_id, key="send-2")
    execution_id = await _record_success(org_id, other)

    status, _ = await api.call(
        "GET", f"/v1/orgs/{org_id}/runs/{mine}/executions/{execution_id}", "alice"
    )

    assert status == 404


async def test_a_colleague_cannot_open_your_evidence(api: Api) -> None:
    """The same 404 the conversation gives them, for the same reason."""
    org_id = await _org(api)
    _, invitation = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/invitations",
        "alice",
        {"email": "bob@example.com", "role": "reader"},
    )
    await api.call("POST", "/v1/invitations/accept", "bob", {"token": invitation["token"]})
    run_id = await _run(api, org_id)
    execution_id = await _record_success(org_id, run_id)

    status, _ = await api.call(
        "GET", f"/v1/orgs/{org_id}/runs/{run_id}/executions/{execution_id}", "bob"
    )

    assert status == 404


async def test_an_execution_from_another_organization_is_not_found(api: Api) -> None:
    """The tenant boundary, with Alice a member of both — so it is RLS proving it."""
    acme = await _org(api)
    globex = await _org(api, name="Globex")
    theirs = await _run(api, globex, key="send-globex")
    execution_id = await _record_success(globex, theirs)

    status, _ = await api.call(
        "GET", f"/v1/orgs/{acme}/runs/{theirs}/executions/{execution_id}", "alice"
    )

    assert status == 404


async def test_an_execution_that_does_not_exist_is_not_found(api: Api) -> None:
    org_id = await _org(api)
    run_id = await _run(api, org_id)

    status, _ = await api.call(
        "GET", f"/v1/orgs/{org_id}/runs/{run_id}/executions/{uuid.uuid4()}", "alice"
    )

    assert status == 404


async def test_the_route_needs_a_token(api: Api) -> None:
    org_id = await _org(api)
    run_id = await _run(api, org_id)
    execution_id = await _record_success(org_id, run_id)

    status, _ = await api.call(
        "GET", f"/v1/orgs/{org_id}/runs/{run_id}/executions/{execution_id}", ""
    )

    assert status == 401
