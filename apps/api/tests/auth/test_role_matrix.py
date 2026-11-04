"""The role matrix, asserted route by route and snapshotted."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from charie.auth.jwt_validator import TokenValidator
from charie.auth.principal import Principal, TokenError
from charie.catalog import routes as catalog_routes
from charie.config import Settings
from charie.db import engine as engine_module
from charie.knowledge import routes as knowledge_routes
from charie.main import create_app
from charie.secrets.local import LocalSecretsProvider
from charie.semantic import proposals as proposals_service
from charie.tenancy import session as session_module

SNAPSHOT = Path(__file__).with_name("role_matrix.json")

ROLES = ("admin", "contributor", "reader")

#: Routes that are not org-scoped, and so are not part of this matrix.
NOT_ORG_SCOPED = {
    ("GET", "/healthz"),
    ("GET", "/v1/me"),
    ("POST", "/v1/orgs"),
    ("POST", "/v1/invitations/accept"),
    # B-017. Claiming a recovery grant cannot be org-scoped.
    ("POST", "/v1/recovery-grants/claim"),
    ("GET", "/dev/token"),
    ("GET", "/dev/jwks.json"),
    ("GET", "/dev/.well-known/openid-configuration"),
}

#: One representative request per org-scoped route.
PROBES: tuple[tuple[str, str, dict[str, Any] | None], ...] = (
    ("GET", "/v1/orgs/{org_id}/members", None),
    ("PATCH", "/v1/orgs/{org_id}/members/{user_id}", {"role": "reader"}),
    ("DELETE", "/v1/orgs/{org_id}/members/{user_id}", None),
    (
        "POST",
        "/v1/orgs/{org_id}/invitations",
        {"email": "invitee@example.com", "role": "reader"},
    ),
    # B-017. A recovery grant makes whoever holds its token an Admin of this organization.
    ("POST", "/v1/orgs/{org_id}/recovery-grants", {"label": "Probe"}),
    ("GET", "/v1/orgs/{org_id}/recovery-grants", None),
    (
        "POST",
        "/v1/orgs/{org_id}/recovery-grants/{grant_id}/revoke",
        {},
    ),
    ("GET", "/v1/orgs/{org_id}/active-data-source", None),
    ("PUT", "/v1/orgs/{org_id}/active-data-source", {"data_source_id": None}),
    ("GET", "/v1/orgs/{org_id}/show-run-cost", None),
    ("PUT", "/v1/orgs/{org_id}/show-run-cost", {"visible": True}),
    ("GET", "/v1/orgs/{org_id}/data-sources", None),
    (
        "POST",
        "/v1/orgs/{org_id}/data-sources",
        {
            "name": "Probe",
            "engine": "pg",
            "host": "127.0.0.1",
            "port": 5432,
            "database": "probe",
            "username": "probe_user",
            "password": "probe-password",
        },
    ),
    ("GET", "/v1/orgs/{org_id}/data-sources/{data_source_id}", None),
    ("PATCH", "/v1/orgs/{org_id}/data-sources/{data_source_id}", {"name": "Probed"}),
    # Port 1 on loopback: refused immediately on every platform.
    ("POST", "/v1/orgs/{org_id}/data-sources/{data_source_id}/test", None),
    # Reading a catalog is member work; building one reaches out to a customer's database.
    ("GET", "/v1/orgs/{org_id}/data-sources/{data_source_id}/catalog", None),
    ("POST", "/v1/orgs/{org_id}/data-sources/{data_source_id}/refresh", None),
    # Profiling reads a customer's rows, so it sits with refresh: Contributor or Admin.
    ("POST", "/v1/orgs/{org_id}/data-sources/{data_source_id}/profile", None),
    (
        "PATCH",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/columns/{column_id}/policy",
        {"policy": "mask", "reason": "probe"},
    ),
    # Searching reads cards, whose examples were masked before they were stored.
    ("GET", "/v1/orgs/{org_id}/catalog/search", None),
    # Asking questions and reading your own traces is granted to every role (architecture 6.2).
    ("POST", "/v1/orgs/{org_id}/conversations", {"title": "Probe"}),
    ("GET", "/v1/orgs/{org_id}/conversations", None),
    ("GET", "/v1/orgs/{org_id}/conversations/{conversation_id}", None),
    # Every role has its own conversations (arch 6.2).
    ("PATCH", "/v1/orgs/{org_id}/conversations/{conversation_id}", {"title": "Renamed"}),
    (
        "POST",
        "/v1/orgs/{org_id}/conversations/{conversation_id}/archive",
        {"archived": False},
    ),
    ("GET", "/v1/orgs/{org_id}/conversations/{conversation_id}/messages", None),
    (
        "POST",
        "/v1/orgs/{org_id}/conversations/{conversation_id}/messages",
        {"content": "How many orders?", "idempotency_key": "probe"},
    ),
    # The answers in a thread, which the screen reads to render each one as more than its words.
    ("GET", "/v1/orgs/{org_id}/conversations/{conversation_id}/runs", None),
    ("GET", "/v1/orgs/{org_id}/runs/{run_id}", None),
    ("GET", "/v1/orgs/{org_id}/runs/{run_id}/events", None),
    # Resolving your own citation is part of reading your own trace.
    ("GET", "/v1/orgs/{org_id}/runs/{run_id}/executions/{execution_id}", None),
    # The semantic layer (WP10.2d, B-059).
    ("GET", "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions", None),
    ("GET", "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/proposals", None),
    (
        "POST",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions",
        {"name": "probe metric", "description": "A metric, for probing."},
    ),
    (
        "POST",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/import",
        {
            "table": "probe",
            "name_column": "probe_column",
            "description_column": "probe_column",
        },
    ),
    (
        "POST",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/accept",
        {"required_filters": []},
    ),
    (
        "POST",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/reject",
        None,
    ),
    # Editing and retiring an active definition (B-088).
    (
        "PATCH",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}",
        {"description": "A metric, corrected."},
    ),
    (
        "DELETE",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}",
        None,
    ),
    (
        "GET",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/versions",
        None,
    ),
    # Bringing one back (B-094). Admin like every other verb here, and for the sharpest reason.
    (
        "POST",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}/reinstate",
        None,
    ),
    # Verified queries (arch 5.4). Admin like the rest of the semantic layer.
    ("GET", "/v1/orgs/{org_id}/data-sources/{data_source_id}/verified-queries", None),
    (
        "POST",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/verified-queries",
        {"question": "How many probes?", "sql": "SELECT probe_column FROM probe"},
    ),
    (
        "DELETE",
        "/v1/orgs/{org_id}/data-sources/{data_source_id}/verified-queries/{verified_query_id}",
        None,
    ),
    ("DELETE", "/v1/orgs/{org_id}/data-sources/{data_source_id}", None),
    # Documents (WP10.1b). Reading is member work like browsing a catalog.
    ("POST", "/v1/orgs/{org_id}/documents", None),
    ("GET", "/v1/orgs/{org_id}/documents", None),
    ("GET", "/v1/orgs/{org_id}/documents/search", None),
    ("GET", "/v1/orgs/{org_id}/documents/supported-types", None),
    ("POST", "/v1/orgs/{org_id}/documents/{document_id}/reindex", None),
    ("DELETE", "/v1/orgs/{org_id}/documents/{document_id}", None),
)


#: Which definition row a probe acts upon.
DEFINITIONS = "/v1/orgs/{org_id}/data-sources/{data_source_id}/definitions/{definition_id}"
PROPOSAL_POOL: dict[str, str] = {
    f"{DEFINITIONS}/reject": "rejected",
    DEFINITIONS: "edited",
    f"{DEFINITIONS}/versions": "edited",
    # Its own pool, already `retired`.
    f"{DEFINITIONS}/reinstate": "reinstated",
}

#: Query strings for routes that require one.
QUERIES: dict[str, str] = {
    "/v1/orgs/{org_id}/catalog/search": "?q=orders",
    "/v1/orgs/{org_id}/documents/search": "?q=revenue",
}

#: Routes that take a file rather than a JSON body.
UPLOADS: dict[str, dict[str, tuple[str, bytes, str]]] = {
    "/v1/orgs/{org_id}/documents": {
        "file": (
            "probe.md",
            b"# Probe\n\nA document long enough for the extractor to accept it.\n",
            "text/markdown",
        )
    }
}


class _SubjectAsToken(TokenValidator):
    def __init__(self) -> None:
        pass

    async def validate(self, token: str) -> Principal:
        if not token:
            raise TokenError("malformed", "nope")
        return Principal(subject=token, email=f"{token}@example.com")


@dataclass(frozen=True)
class Matrix:
    """One organization, a member of every role, and something to act upon."""

    app: FastAPI
    org_id: uuid.UUID
    users: dict[str, uuid.UUID]
    data_source_id: uuid.UUID
    column_id: uuid.UUID
    #: A conversation and a run per role.
    conversations: dict[str, uuid.UUID]
    runs: dict[str, uuid.UUID]
    #: One `query_executions` row per role, on that role's own run.
    executions: dict[str, uuid.UUID]
    #: Five definitions per role: one each for the accept, reject, retire and reinstate probes.
    proposals: dict[str, dict[str, uuid.UUID]]
    #: One approved example per role, for the same reason the proposals are per role.
    verified: dict[str, uuid.UUID]
    #: One recovery grant for the organization (B-017).
    recovery_grant_id: uuid.UUID
    #: A document per role, and for a blunter reason than the conversations.
    documents: dict[str, uuid.UUID]


@pytest.fixture
async def matrix_app(
    app_database: URL,
    migrated_database: URL,
    secrets_provider: LocalSecretsProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Matrix]:
    """One organization holding a member of every role, plus a spare target."""
    owner = create_async_engine(migrated_database)
    app_engine = create_async_engine(app_database)
    monkeypatch.setattr(engine_module, "get_engine", lambda: owner)
    monkeypatch.setattr(
        session_module,
        "_session_factory",
        lambda: async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False),
    )
    # The upload probe posts a real file through a real ingest.
    monkeypatch.setattr(knowledge_routes, "document_embedder", lambda: None)
    # And the same for cards: refreshing a catalog embeds them since B-018.
    monkeypatch.setattr(catalog_routes, "card_embedder", lambda: None)

    # The import probe reads the customer's database through the DAL.
    async def _no_rows(**_: object) -> tuple[object, ...]:
        return ()

    monkeypatch.setattr(proposals_service, "propose_from_table", _no_rows)

    org_id = uuid.uuid4()
    data_source_id = uuid.uuid4()
    column_id = uuid.uuid4()
    users: dict[str, uuid.UUID] = {}
    conversations: dict[str, uuid.UUID] = {}
    proposals: dict[str, dict[str, uuid.UUID]] = {
        "accepted": {},
        "rejected": {},
        # Active rather than proposed: PATCH and DELETE act on a definition that is already in...
        "edited": {},
        "retired": {},
        # And this one starts out of force, because that is the only state `reinstate` accepts.
        "reinstated": {},
    }
    verified: dict[str, uuid.UUID] = {}
    documents: dict[str, uuid.UUID] = {}
    runs: dict[str, uuid.UUID] = {}
    executions: dict[str, uuid.UUID] = {}
    async with owner.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.org_id', :org, true)"), {"org": str(org_id)}
        )
        await connection.execute(
            text("INSERT INTO organizations (id, name) VALUES (:id, 'Matrix')"), {"id": org_id}
        )
        # Two admins, so that a PATCH or DELETE aimed at one is refused on role grounds only.
        for subject, role in (
            ("admin", "admin"),
            ("spare-admin", "admin"),
            ("contributor", "contributor"),
            ("reader", "reader"),
        ):
            user_id = uuid.uuid4()
            users[subject] = user_id
            await connection.execute(
                text("INSERT INTO users (id, external_subject, email) VALUES (:i, :s, :e)"),
                {"i": user_id, "s": subject, "e": f"{subject}@example.com"},
            )
            await connection.execute(
                text("INSERT INTO org_memberships (org_id, user_id, role) VALUES (:o, :u, :r)"),
                {"o": org_id, "u": user_id, "r": role},
            )
            # Each probing role gets a conversation of its own, and a run in it.
            if subject in ROLES:
                conversation_id, run_id = uuid.uuid4(), uuid.uuid4()
                conversations[subject], runs[subject] = conversation_id, run_id
                document_id = uuid.uuid4()
                documents[subject] = document_id
                await connection.execute(
                    text(
                        "INSERT INTO knowledge_documents "
                        "(id, org_id, title, blob_path, mime, status) "
                        "VALUES (:i, :o, 'Probe', :p, 'text/markdown', 'indexed')"
                    ),
                    {"i": document_id, "o": org_id, "p": f"{org_id}/docs/{document_id}.md"},
                )
                await connection.execute(
                    text(
                        "INSERT INTO conversations (id, org_id, user_id, title) "
                        "VALUES (:i, :o, :u, 'Probe')"
                    ),
                    {"i": conversation_id, "o": org_id, "u": user_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO agent_runs (id, org_id, conversation_id, user_id, status, "
                        "question) VALUES (:i, :o, :c, :u, 'queued', 'How many orders?')"
                    ),
                    {"i": run_id, "o": org_id, "c": conversation_id, "u": user_id},
                )
                execution_id = uuid.uuid4()
                executions[subject] = execution_id
                await connection.execute(
                    text(
                        "INSERT INTO query_executions (id, org_id, run_id, actor_user_id, "
                        "sql_text, sql_hash, status, row_count) "
                        "VALUES (:i, :o, :r, :u, 'SELECT 1', 'probehash', 'ok', 1)"
                    ),
                    {"i": execution_id, "o": org_id, "r": run_id, "u": user_id},
                )
        # Port 1 is refused instantly, so the /test probe never waits on a socket.
        await connection.execute(
            text(
                "INSERT INTO data_sources (id, org_id, name, engine, host_display, "
                "settings, secret_ref) VALUES (:i, :o, 'Matrix source', 'pg', "
                "'127.0.0.1:1/probe', :s, :r)"
            ),
            {
                "i": data_source_id,
                "o": org_id,
                "s": '{"host": "127.0.0.1", "port": 1, "database": "probe", '
                '"username_last4": "obe"}',
                "r": f"ds/{org_id}/{data_source_id}/credentials",
            },
        )
        # A catalog with one column in it, written directly rather than discovered.
        snapshot_id = uuid.uuid4()
        table_id = uuid.uuid4()
        await connection.execute(
            text(
                "INSERT INTO catalog_snapshots (id, org_id, data_source_id, version, status) "
                "VALUES (:i, :o, :d, 1, 'active')"
            ),
            {"i": snapshot_id, "o": org_id, "d": data_source_id},
        )
        await connection.execute(
            text(
                "INSERT INTO catalog_tables (id, org_id, snapshot_id, schema_name, table_name, "
                "kind, structural_hash) VALUES (:i, :o, :s, 'public', 'probe', 'table', :h)"
            ),
            {"i": table_id, "o": org_id, "s": snapshot_id, "h": uuid.uuid4().hex},
        )
        await connection.execute(
            text(
                "INSERT INTO catalog_columns (id, org_id, table_id, name, ordinal, data_type, "
                "nullable) VALUES (:i, :o, :t, 'probe_column', 1, 'text', true)"
            ),
            {"i": column_id, "o": org_id, "t": table_id},
        )

        # A proposal per role per verb. Written directly rather than imported.
        for role in ROLES:
            for pool in ("accepted", "rejected", "edited", "retired", "reinstated"):
                proposal_id = uuid.uuid4()
                proposals[pool][role] = proposal_id
                status = {
                    "accepted": "proposed",
                    "rejected": "proposed",
                    "reinstated": "retired",
                }.get(pool, "active")
                await connection.execute(
                    text(
                        "INSERT INTO semantic_definitions "
                        "(id, org_id, data_source_id, name, kind, description, status) "
                        "VALUES (:i, :o, :d, :n, 'metric', 'A definition, for probing.', :s)"
                    ),
                    {
                        "i": proposal_id,
                        "o": org_id,
                        "d": data_source_id,
                        "n": f"{pool} {role}",
                        "s": status,
                    },
                )
            example_id = uuid.uuid4()
            verified[role] = example_id
            await connection.execute(
                text(
                    "INSERT INTO verified_queries "
                    "(id, org_id, data_source_id, question, sql) "
                    "VALUES (:i, :o, :d, :q, 'SELECT probe_column FROM probe')"
                ),
                {"i": example_id, "o": org_id, "d": data_source_id, "q": f"probe {role}?"},
            )

        # B-017. One grant serves all three roles: revoking is idempotent.
        recovery_grant_id = uuid.uuid4()
        await connection.execute(
            text(
                "INSERT INTO org_recovery_grants "
                "(id, org_id, token_hash, label, expires_at) "
                "VALUES (:i, :o, :h, 'probe', now() + interval '365 days')"
            ),
            {"i": recovery_grant_id, "o": org_id, "h": f"probe-hash-{recovery_grant_id}"},
        )

    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken()

    try:
        yield Matrix(
            app=app,
            org_id=org_id,
            users=users,
            data_source_id=data_source_id,
            column_id=column_id,
            conversations=conversations,
            runs=runs,
            executions=executions,
            documents=documents,
            proposals=proposals,
            verified=verified,
            recovery_grant_id=recovery_grant_id,
        )
    finally:
        await owner.dispose()
        await app_engine.dispose()


def _pool(method: str, template: str) -> str:
    """Which pool of definitions this probe draws from."""
    if method == "DELETE" and template == DEFINITIONS:
        return "retired"
    return PROPOSAL_POOL.get(template, "accepted")


async def _probe(
    app: FastAPI,
    method: str,
    path: str,
    who: str,
    body: dict[str, Any] | None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> int:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {who}"},
            # Never both: httpx refuses a request carrying a JSON body and a multipart one.
            json=body if files is None else None,
            files=files,
        )
    return response.status_code


async def test_the_role_matrix_matches_its_snapshot(matrix_app: Matrix) -> None:
    """Observe who may do what, then compare with the committed record."""
    observed: dict[str, dict[str, str]] = {}
    for method, template, body in PROBES:
        key = f"{method} {template}"
        observed[key] = {}
        for role in ROLES:
            # Formatted per role rather than once: the conversation and run ids differ by caller.
            path = template.format(
                org_id=matrix_app.org_id,
                user_id=matrix_app.users["spare-admin"],
                data_source_id=matrix_app.data_source_id,
                column_id=matrix_app.column_id,
                conversation_id=matrix_app.conversations[role],
                run_id=matrix_app.runs[role],
                execution_id=matrix_app.executions[role],
                document_id=matrix_app.documents[role],
                definition_id=matrix_app.proposals[_pool(method, template)][role],
                verified_query_id=matrix_app.verified[role],
                grant_id=matrix_app.recovery_grant_id,
            ) + QUERIES.get(template, "")
            status = await _probe(matrix_app.app, method, path, role, body, UPLOADS.get(template))
            observed[key][role] = "allow" if status < 400 else f"deny({status})"

    rendered = json.dumps(observed, indent=2, sort_keys=True) + "\n"

    if not SNAPSHOT.exists():  # pragma: no cover - first run only
        SNAPSHOT.write_text(rendered, encoding="utf-8", newline="")
        pytest.fail(f"wrote a new snapshot to {SNAPSHOT.name}; review it and re-run")

    expected = SNAPSHOT.read_text(encoding="utf-8")
    assert rendered == expected, (
        "the role matrix changed. If that was intended, update "
        f"{SNAPSHOT.name} in this PR so the change is reviewed."
    )


async def test_the_snapshot_says_what_the_architecture_says(matrix_app: Matrix) -> None:
    """A snapshot only proves stability."""
    recorded = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    for readable in (
        "GET /v1/orgs/{org_id}/members",
        "GET /v1/orgs/{org_id}/data-sources",
        "GET /v1/orgs/{org_id}/data-sources/{data_source_id}",
        # D-045. Readable by any member on purpose.
        "GET /v1/orgs/{org_id}/active-data-source",
        # D-066, and readable for the same reason.
        "GET /v1/orgs/{org_id}/show-run-cost",
        # "Ask questions / view own conversations & traces" is the one line of 6.2's table that...
        "POST /v1/orgs/{org_id}/conversations",
        "GET /v1/orgs/{org_id}/conversations",
        "GET /v1/orgs/{org_id}/conversations/{conversation_id}",
        "GET /v1/orgs/{org_id}/conversations/{conversation_id}/messages",
        "POST /v1/orgs/{org_id}/conversations/{conversation_id}/messages",
        "GET /v1/orgs/{org_id}/conversations/{conversation_id}/runs",
        "GET /v1/orgs/{org_id}/runs/{run_id}",
        "GET /v1/orgs/{org_id}/runs/{run_id}/events",
        # A trace whose citations cannot be opened is a trace you are asked to take on faith.
        "GET /v1/orgs/{org_id}/runs/{run_id}/executions/{execution_id}",
    ):
        assert recorded[readable] == {
            "admin": "allow",
            "contributor": "allow",
            "reader": "allow",
        }
    # Reading the organization's documents is member work, like browsing a catalog.
    for readable_document_route in (
        "GET /v1/orgs/{org_id}/documents",
        "GET /v1/orgs/{org_id}/documents/search",
        "GET /v1/orgs/{org_id}/documents/supported-types",
    ):
        assert recorded[readable_document_route] == {
            "admin": "allow",
            "contributor": "allow",
            "reader": "allow",
        }
    # Writing one is Contributor-or-Admin (architecture 10.2 marks the route `[contributor+]`).
    for contributor_only in (
        "POST /v1/orgs/{org_id}/documents",
        "POST /v1/orgs/{org_id}/documents/{document_id}/reindex",
        "DELETE /v1/orgs/{org_id}/documents/{document_id}",
    ):
        assert recorded[contributor_only]["admin"] == "allow"
        assert recorded[contributor_only]["contributor"] == "allow"
        assert recorded[contributor_only]["reader"] == "deny(403)"
    for admin_only in (
        "PATCH /v1/orgs/{org_id}/members/{user_id}",
        "DELETE /v1/orgs/{org_id}/members/{user_id}",
        "POST /v1/orgs/{org_id}/invitations",
        "POST /v1/orgs/{org_id}/data-sources",
        "PATCH /v1/orgs/{org_id}/data-sources/{data_source_id}",
        "DELETE /v1/orgs/{org_id}/data-sources/{data_source_id}",
        "POST /v1/orgs/{org_id}/data-sources/{data_source_id}/test",
        # D-045. Choosing the database an entire organization answers from is org-shaping.
        "PUT /v1/orgs/{org_id}/active-data-source",
        # D-066. Not a permission — off hides spend from the whole organization.
        "PUT /v1/orgs/{org_id}/show-run-cost",
    ):
        assert recorded[admin_only]["admin"] == "allow"
        assert recorded[admin_only]["contributor"].startswith("deny")
        assert recorded[admin_only]["reader"].startswith("deny")


def test_every_org_route_is_covered() -> None:
    """A new org-scoped route with no probe is a role nobody decided on."""
    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))

    # Read the OpenAPI schema rather than walking app.routes.
    paths = app.openapi()["paths"]
    exposed = {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if method.upper() != "HEAD"
    }
    probed = {(method, template) for method, template, _ in PROBES}
    org_scoped = {
        (method, path)
        for method, path in exposed
        if "{org_id}" in path and (method, path) not in NOT_ORG_SCOPED
    }

    assert org_scoped == probed, (
        "org-scoped routes and the role matrix disagree. Unprobed routes: "
        f"{sorted(org_scoped - probed)}; probes for routes that no longer exist: "
        f"{sorted(probed - org_scoped)}"
    )
