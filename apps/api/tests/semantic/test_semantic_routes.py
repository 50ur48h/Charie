"""The semantic layer over HTTP (plan WP10.2d, B-059)."""

from __future__ import annotations

from collections.abc import AsyncIterator
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
from charie.main import create_app
from charie.secrets.local import LocalSecretsProvider
from charie.tenancy import session as session_module
from customer_db import CustomerDatabase

BOOK = "metric_book"


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
    app_database: URL,
    migrated_database: URL,
    secrets_provider: LocalSecretsProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Api]:
    owner = create_async_engine(migrated_database)
    app_engine = create_async_engine(app_database)
    monkeypatch.setattr(engine_module, "get_engine", lambda: owner)
    monkeypatch.setattr(
        session_module,
        "_session_factory",
        lambda: async_sessionmaker(app_engine, expire_on_commit=False, autoflush=False),
    )
    # These tests refresh a catalog, which embeds its cards since B-018.
    monkeypatch.setattr(catalog_routes, "card_embedder", lambda: None)
    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken()
    try:
        yield Api(app)
    finally:
        await owner.dispose()
        await app_engine.dispose()


async def _metric_table(customer: CustomerDatabase) -> None:
    """The customer's own metric book, standing in for a customer `meta_metric` table."""
    engine = create_async_engine(customer.url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BOOK} ("
                    "  metric_key text PRIMARY KEY,"
                    "  definition_text text,"
                    "  formula text,"
                    "  also_called text,"
                    "  caution text)"
                )
            )
            await connection.execute(text(f"DELETE FROM {BOOK}"))
            await connection.execute(
                text(
                    f"INSERT INTO {BOOK} "
                    "(metric_key, definition_text, formula, also_called, caution) "
                    "VALUES ('stock_value', "
                    "'Total price of everything we list, excluding samples.', "
                    "'sum(products.price)', 'stock value, listed value', "
                    "'Samples are excluded, so this understates what is on the shelf.')"
                )
            )
            await connection.execute(text(f"GRANT SELECT ON {BOOK} TO {customer.reader_username}"))
    finally:
        await engine.dispose()


async def _org_with_catalog(api: Api, customer: CustomerDatabase) -> tuple[str, str]:
    """An organization, a verified data source, and a catalog to validate against."""
    _, org = await api.call("POST", "/v1/orgs", "alice", {"name": "Acme"})
    org_id = str(org["org_id"])
    _, created = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources",
        "alice",
        {
            "name": "Customer",
            "engine": "pg",
            "host": customer.host,
            "port": customer.port,
            "database": customer.database,
            "username": customer.reader_username,
            "password": customer.reader_password,
            "tls_mode": "prefer",
        },
    )
    source_id = str(created["id"])
    await api.call("POST", f"/v1/orgs/{org_id}/data-sources/{source_id}/test", "alice")
    await api.call("POST", f"/v1/orgs/{org_id}/data-sources/{source_id}/refresh", "alice")
    return org_id, source_id


def _import_body() -> dict[str, Any]:
    return {
        "table": BOOK,
        "name_column": "metric_key",
        "description_column": "definition_text",
        "expression_column": "formula",
        "synonyms_column": "also_called",
    }


# --- Writing one by hand ---


async def test_an_admin_writes_a_definition_and_it_binds(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, created = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions",
        "alice",
        {
            "name": "Listed value",
            "description": "What everything we list is worth.",
            "synonyms": ["stock value"],
            "required_filters": [
                {"table": "products", "column": "price", "op": "gt", "values": ["0"]}
            ],
        },
    )

    assert status == 201
    # Lowercased, because "Listed value" and "listed_value" are one metric and a catalog of...
    assert created["name"] == "listed value"
    assert created["binds"] is True
    assert created["required_filters"][0]["column"] == "price"

    status, listed = await api.call(
        "GET", f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions", "alice"
    )
    assert status == 200
    assert [item["name"] for item in listed] == ["listed value"]


async def test_a_filter_on_a_column_that_does_not_exist_is_refused_at_the_door(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """And the 400 names the column."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, body = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions",
        "alice",
        {
            "name": "nonsense",
            "description": "Requires something this database has never had.",
            "required_filters": [
                {"table": "products", "column": "no_such_column", "op": "eq", "values": ["1"]}
            ],
        },
    )

    assert status == 400
    assert "no_such_column" in body["detail"]

    _, listed = await api.call(
        "GET", f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions", "alice"
    )
    assert listed == []


async def test_an_operator_the_critic_cannot_check_is_refused(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The operator set is closed on purpose."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, body = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions",
        "alice",
        {
            "name": "roughly",
            "description": "Approximately something.",
            "required_filters": [
                {"table": "products", "column": "price", "op": "like", "values": ["%a%"]}
            ],
        },
    )

    assert status == 400
    assert "filter operator" in body["detail"]


# --- Importing what the database already carries ---


async def test_an_import_proposes_and_binds_nothing(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The property the whole design turns on, asserted at the route."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, proposed = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions/import",
        "alice",
        _import_body(),
    )

    assert status == 201
    assert [item["name"] for item in proposed] == ["stock_value"]
    assert "excluding samples" in proposed[0]["description"]
    assert proposed[0]["provenance"]["table"] == f"public.{BOOK}"

    _, waiting = await api.call(
        "GET", f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions/proposals", "alice"
    )
    assert [item["name"] for item in waiting] == ["stock_value"]

    _, active = await api.call(
        "GET", f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions", "alice"
    )
    assert active == []


async def test_importing_a_table_the_catalog_does_not_know_is_a_400(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Refused by the DAL, which grounds every read against the catalog."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, body = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions/import",
        "alice",
        {**_import_body(), "table": "not_a_table"},
    )

    assert status == 400
    assert "not_a_table" in body["detail"]


async def test_a_table_name_that_is_not_a_bare_identifier_is_refused_before_any_sql(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The cheap half of 5.10's two independent layers."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, body = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions/import",
        "alice",
        {**_import_body(), "table": "metric_book; DROP TABLE shops"},
    )

    assert status == 400
    assert "table name" in body["detail"]


async def test_an_imported_caveat_survives_acceptance_and_reaches_the_wire(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The whole travel, because every stop on it could drop the sentence."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    sentence = "Samples are excluded, so this understates what is on the shelf."

    _, proposed = await api.call(
        "POST", f"{base}/import", "alice", {**_import_body(), "caveat_column": "caution"}
    )
    # The reviewer has to see what they are about to bless.
    assert proposed[0]["caveat"] == sentence

    _, accepted = await api.call("POST", f"{base}/{proposed[0]['id']}/accept", "alice", {})
    assert accepted["caveat"] == sentence

    _, listed = await api.call("GET", base, "alice")
    assert [row["caveat"] for row in listed if row["name"] == "stock_value"] == [sentence]


async def test_an_unmapped_caveat_column_leaves_the_definition_without_one(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Most metrics are just a formula and should not be made to sound uncertain."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"

    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())

    assert proposed[0]["caveat"] is None


async def test_a_second_import_does_not_re_propose_what_is_already_known(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    path = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions/import"

    await api.call("POST", path, "alice", _import_body())
    status, again = await api.call("POST", path, "alice", _import_body())

    # 201 with nothing in it: the request succeeded and proposed nothing.
    assert status == 201
    assert again == []


# --- Accepting is where prose becomes a constraint ---


async def test_accepting_with_filters_is_what_makes_a_definition_bind(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """D-033, at the moment it happens."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())
    definition_id = proposed[0]["id"]

    status, accepted = await api.call(
        "POST",
        f"{base}/{definition_id}/accept",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "price", "op": "gt", "values": ["0"]}
            ]
        },
    )

    assert status == 200
    assert accepted["binds"] is True

    _, active = await api.call("GET", base, "alice")
    assert [item["name"] for item in active] == ["stock_value"]

    _, waiting = await api.call("GET", f"{base}/proposals", "alice")
    assert waiting == []


async def test_accepting_without_filters_is_prose_and_says_so(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """An Admin may bless a definition as prose."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())

    status, accepted = await api.call(
        "POST", f"{base}/{proposed[0]['id']}/accept", "alice", {"required_filters": []}
    )

    assert status == 200
    assert accepted["binds"] is False
    assert accepted["required_filters"] == []


async def test_accepting_with_a_filter_this_database_cannot_support_leaves_it_proposed(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Validated before the row is activated."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())

    status, body = await api.call(
        "POST",
        f"{base}/{proposed[0]['id']}/accept",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "invented", "op": "eq", "values": ["1"]}
            ]
        },
    )

    assert status == 400
    assert "invented" in body["detail"]

    _, active = await api.call("GET", base, "alice")
    assert active == []
    _, waiting = await api.call("GET", f"{base}/proposals", "alice")
    assert [item["name"] for item in waiting] == ["stock_value"]


async def test_accepting_the_same_proposal_twice_is_a_404(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """It is no longer a proposal."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())
    accept = f"{base}/{proposed[0]['id']}/accept"

    await api.call("POST", accept, "alice", {"required_filters": []})
    status, _ = await api.call("POST", accept, "alice", {"required_filters": []})

    assert status == 404


async def test_rejecting_retires_a_proposal_rather_than_deleting_it(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """So that "we looked at this and said no" is answerable."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())

    status, _ = await api.call("POST", f"{base}/{proposed[0]['id']}/reject", "alice")

    assert status == 204
    _, waiting = await api.call("GET", f"{base}/proposals", "alice")
    assert waiting == []
    _, active = await api.call("GET", base, "alice")
    assert active == []

    # The name is still taken, which is what "retired rather than deleted" buys.
    _, again = await api.call("POST", f"{base}/import", "alice", _import_body())
    assert again == []


async def test_a_definition_from_another_organization_is_a_404(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Not a filtered view of somebody else's proposal — an absent one."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())

    _, other = await api.call("POST", "/v1/orgs", "dave", {"name": "Globex"})
    other_org = str(other["org_id"])

    status, _ = await api.call(
        "POST",
        f"/v1/orgs/{other_org}/data-sources/{source_id}/definitions/{proposed[0]['id']}/accept",
        "dave",
        {"required_filters": []},
    )

    assert status == 404


# --- Correcting one, which used to require psql (B-088) ---


async def _active_definition(api: Api, org_id: str, source_id: str) -> dict[str, Any]:
    """One definition in force, written by hand and binding nothing yet."""
    _, created = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions",
        "alice",
        {
            "name": "listed value",
            "description": "What everything we list is worth.",
            "synonyms": ["stock value"],
        },
    )
    return dict(created)


async def test_an_admin_gives_an_active_definition_the_filter_it_should_have_had(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """B-088, the whole of it."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    assert definition["binds"] is False

    status, edited = await api.call(
        "PATCH",
        f"{base}/{definition['id']}",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "price", "op": "gt", "values": ["0"]}
            ]
        },
    )

    assert status == 200
    assert edited["binds"] is True
    assert edited["version"] == 2

    _, active = await api.call("GET", base, "alice")
    assert active[0]["required_filters"][0]["column"] == "price"
    # The rest of the definition is untouched.
    assert active[0]["description"] == definition["description"]
    assert active[0]["synonyms"] == definition["synonyms"]


async def test_an_edit_is_validated_exactly_as_acceptance_is(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """And the definition is left exactly as it was."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)

    status, body = await api.call(
        "PATCH",
        f"{base}/{definition['id']}",
        "alice",
        {
            "description": "Corrected.",
            "required_filters": [
                {"table": "products", "column": "invented", "op": "eq", "values": ["1"]}
            ],
        },
    )

    assert status == 400
    assert "invented" in body["detail"]

    _, active = await api.call("GET", base, "alice")
    assert active[0]["description"] == definition["description"]
    assert active[0]["version"] == 1


async def test_an_empty_filter_list_stops_the_enforcement_and_keeps_the_prose(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The other direction, and the one that matters most in practice."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call(
        "PATCH",
        f"{base}/{definition['id']}",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "price", "op": "gt", "values": ["0"]}
            ]
        },
    )

    status, unbound = await api.call(
        "PATCH", f"{base}/{definition['id']}", "alice", {"required_filters": []}
    )

    assert status == 200
    assert unbound["binds"] is False
    assert unbound["required_filters"] == []
    assert unbound["description"] == definition["description"]


async def test_omitting_a_field_leaves_it_alone_and_null_clears_the_formula(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The one place where absent and null differ."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, created = await api.call(
        "POST",
        base,
        "alice",
        {
            "name": "listed value",
            "description": "What everything we list is worth.",
            "expression": "sum(products.price)",
            "synonyms": ["stock value"],
        },
    )

    _, kept = await api.call(
        "PATCH", f"{base}/{created['id']}", "alice", {"description": "Worth, at list price."}
    )
    assert kept["expression"] == "sum(products.price)"
    assert kept["synonyms"] == ["stock value"]

    _, cleared = await api.call("PATCH", f"{base}/{created['id']}", "alice", {"expression": None})
    assert cleared["expression"] is None
    assert cleared["description"] == "Worth, at list price."


async def test_editing_a_proposal_is_a_404(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """A proposal is accepted, not edited — and `accept` already takes the filters and synonyms."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())

    status, _ = await api.call(
        "PATCH", f"{base}/{proposed[0]['id']}", "alice", {"description": "Rewritten."}
    )

    assert status == 404


async def test_retiring_a_definition_stops_it_binding_without_forgetting_it(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)

    status, _ = await api.call("DELETE", f"{base}/{definition['id']}", "alice")

    assert status == 204
    _, active = await api.call("GET", base, "alice")
    assert active == []

    # Retiring it twice is a 404: it is no longer in force.
    status, _ = await api.call("DELETE", f"{base}/{definition['id']}", "alice")
    assert status == 404
    status, _ = await api.call(
        "PATCH", f"{base}/{definition['id']}", "alice", {"description": "Rewritten."}
    )
    assert status == 404


async def test_a_definitions_history_says_what_it_required_at_each_version(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Why versioning is part of B-088 rather than a later nicety."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call(
        "PATCH",
        f"{base}/{definition['id']}",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "price", "op": "gt", "values": ["0"]}
            ]
        },
    )
    await api.call("DELETE", f"{base}/{definition['id']}", "alice")

    status, history = await api.call("GET", f"{base}/{definition['id']}/versions", "alice")

    assert status == 200
    assert [item["version"] for item in history] == [1, 2, 3]
    assert [item["change"] for item in history] == ["created", "updated", "retired"]
    # Version 1 bound nothing; version 2 is where it started to.
    assert history[0]["required_filters"] == []
    assert history[1]["required_filters"][0]["column"] == "price"
    assert history[2]["status"] == "retired"
    assert all(item["changed_by"] for item in history), "a version says who made it"


async def test_an_edit_that_changes_nothing_writes_no_version(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """A version that says the same as the one before it is noise in the only history anybody..."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)

    status, unchanged = await api.call(
        "PATCH", f"{base}/{definition['id']}", "alice", {"description": definition["description"]}
    )

    assert status == 200
    assert unchanged["version"] == 1
    _, history = await api.call("GET", f"{base}/{definition['id']}/versions", "alice")
    assert [item["version"] for item in history] == [1]


async def test_an_accepted_proposal_starts_its_history_where_it_took_effect(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """A proposal is not a version: it binds nothing while it waits."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())
    definition_id = proposed[0]["id"]

    _, before = await api.call("GET", f"{base}/{definition_id}/versions", "alice")
    assert before == []

    await api.call("POST", f"{base}/{definition_id}/accept", "alice", {"required_filters": []})

    _, history = await api.call("GET", f"{base}/{definition_id}/versions", "alice")
    assert [(item["version"], item["change"]) for item in history] == [(1, "accepted")]


async def test_every_decision_about_a_definition_lands_in_the_audit_log(
    api: Api,
    app_database: URL,
    isolated_customer_database: CustomerDatabase,
) -> None:
    """An edit changes what the platform enforces on generated SQL."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call(
        "PATCH", f"{base}/{definition['id']}", "alice", {"description": "Worth, at list price."}
    )
    await api.call("DELETE", f"{base}/{definition['id']}", "alice")

    engine = create_async_engine(app_database)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": org_id}
            )
            rows = (
                await connection.execute(
                    text("SELECT action, details FROM audit_log WHERE object_id = :id ORDER BY id"),
                    {"id": definition["id"]},
                )
            ).fetchall()
    finally:
        await engine.dispose()

    assert [row[0] for row in rows] == [
        "semantic.definition_created",
        "semantic.definition_updated",
        "semantic.definition_retired",
    ]
    updated = next(row[1] for row in rows if row[0] == "semantic.definition_updated")
    # Which fields moved and which version to read — not the values.
    assert updated["changed"] == ["description"]
    assert updated["version"] == 2


async def test_a_definition_in_another_organization_cannot_be_edited(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Not a filtered view of somebody else's definition — an absent one."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    definition = await _active_definition(api, org_id, source_id)

    _, other = await api.call("POST", "/v1/orgs", "dave", {"name": "Globex"})
    other_org = str(other["org_id"])

    status, _ = await api.call(
        "PATCH",
        f"/v1/orgs/{other_org}/data-sources/{source_id}/definitions/{definition['id']}",
        "dave",
        {"description": "Ours now."},
    )

    assert status == 404


# --- Bringing one back, which used to require psql (B-094) ---


async def test_a_retired_definition_can_be_brought_back_and_the_history_says_so(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """B-094, and the acceptance the owner wrote."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call("DELETE", f"{base}/{definition['id']}", "alice")

    status, back = await api.call("POST", f"{base}/{definition['id']}/reinstate", "alice")

    assert status == 200
    # v1 created, v2 retired, v3 reinstated: one more than it went out on.
    assert back["version"] == 3
    _, active = await api.call("GET", base, "alice")
    assert [item["name"] for item in active] == [definition["name"]]

    _, history = await api.call("GET", f"{base}/{definition['id']}/versions", "alice")
    assert [item["change"] for item in history] == ["created", "retired", "reinstated"]


async def test_reinstating_keeps_the_filters_it_was_retired_holding(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The ordinary case: back as it was, still binding what it bound."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call(
        "PATCH",
        f"{base}/{definition['id']}",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "price", "op": "gt", "values": ["0"]}
            ]
        },
    )
    await api.call("DELETE", f"{base}/{definition['id']}", "alice")

    _, back = await api.call("POST", f"{base}/{definition['id']}/reinstate", "alice")

    assert back["binds"] is True
    assert back["required_filters"][0]["column"] == "price"


async def test_a_definition_whose_catalog_moved_on_is_repaired_as_it_comes_back(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The second dead end, closed in the same act."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call("DELETE", f"{base}/{definition['id']}", "alice")

    status, body = await api.call(
        "POST",
        f"{base}/{definition['id']}/reinstate",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "invented", "op": "eq", "values": ["1"]}
            ]
        },
    )

    assert status == 400
    assert "invented" in body["detail"]
    # Refused means still retired, not half-back.
    _, active = await api.call("GET", base, "alice")
    assert active == []

    status, back = await api.call(
        "POST",
        f"{base}/{definition['id']}/reinstate",
        "alice",
        {
            "required_filters": [
                {"table": "products", "column": "price", "op": "gt", "values": ["0"]}
            ]
        },
    )

    assert status == 200
    assert back["required_filters"][0]["column"] == "price"


async def test_reinstating_something_that_is_not_retired_is_a_404(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """An active definition has nothing to come back from."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)

    status, _ = await api.call("POST", f"{base}/{definition['id']}/reinstate", "alice")
    assert status == 404

    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())
    status, _ = await api.call("POST", f"{base}/{proposed[0]['id']}/reinstate", "alice")
    assert status == 404


async def test_a_retired_definition_can_be_found_before_it_can_be_reinstated(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Half of B-094 is discoverability."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call("DELETE", f"{base}/{definition['id']}", "alice")

    status, retired = await api.call("GET", f"{base}?status=retired", "alice")

    assert status == 200
    assert [item["name"] for item in retired] == [definition["name"]]

    _, active = await api.call("GET", base, "alice")
    assert active == []


async def test_reinstating_lands_in_the_audit_log_as_its_own_act(
    api: Api,
    app_database: URL,
    isolated_customer_database: CustomerDatabase,
) -> None:
    """Recorded as a reinstatement rather than as an edit, in the audit trail as in the history."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    definition = await _active_definition(api, org_id, source_id)
    await api.call("DELETE", f"{base}/{definition['id']}", "alice")
    await api.call("POST", f"{base}/{definition['id']}/reinstate", "alice")

    engine = create_async_engine(app_database)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": org_id}
            )
            rows = (
                await connection.execute(
                    text("SELECT action FROM audit_log WHERE object_id = :id ORDER BY id"),
                    {"id": definition["id"]},
                )
            ).fetchall()
    finally:
        await engine.dispose()

    assert [row[0] for row in rows] == [
        "semantic.definition_created",
        "semantic.definition_retired",
        "semantic.definition_reinstated",
    ]


# --- Verified queries: approved examples, judged but never run ---


async def test_an_admin_approves_an_example_and_the_planner_can_be_shown_it(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/verified-queries"

    status, created = await api.call(
        "POST",
        base,
        "alice",
        {
            "question": "how many products do we list?",
            "sql": "SELECT count(*) FROM products",
            "notes": "products is unrelated to shops; do not try to join them.",
        },
    )

    assert status == 201
    assert created["question"] == "how many products do we list?"

    status, listed = await api.call("GET", base, "alice")
    assert status == 200
    assert [item["sql"] for item in listed] == ["SELECT count(*) FROM products"]


async def test_an_example_naming_a_table_that_does_not_exist_is_refused(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """The property this feature most needs."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, body = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/verified-queries",
        "alice",
        {"question": "how much revenue?", "sql": "SELECT sum(total) FROM invoices"},
    )

    assert status == 400
    assert "invoices" in body["detail"]


async def test_an_example_that_is_not_read_only_is_refused(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """An Admin cannot bless a statement the platform would refuse to run."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    status, body = await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/verified-queries",
        "alice",
        {"question": "clear the products", "sql": "DELETE FROM products"},
    )

    assert status == 400
    assert "would run" in body["detail"]


async def test_approving_an_example_reads_no_customer_rows(
    api: Api,
    app_database: URL,
    isolated_customer_database: CustomerDatabase,
) -> None:
    """The statement is judged, not executed."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)

    await api.call(
        "POST",
        f"/v1/orgs/{org_id}/data-sources/{source_id}/verified-queries",
        "alice",
        {"question": "how many products?", "sql": "SELECT count(*) FROM products"},
    )

    engine = create_async_engine(app_database)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": org_id}
            )
            reads = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM query_executions "
                        "WHERE sql_text ILIKE '%count(*) FROM products%'"
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert reads == 0


async def test_retiring_an_example_stops_showing_it_without_forgetting_it(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Retired rather than deleted, so a run grounded in it last month is still explainable..."""
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/verified-queries"
    _, created = await api.call(
        "POST",
        base,
        "alice",
        {"question": "how many products?", "sql": "SELECT count(*) FROM products"},
    )

    status, _ = await api.call("DELETE", f"{base}/{created['id']}", "alice")

    assert status == 204
    _, listed = await api.call("GET", base, "alice")
    assert listed == []

    # Retiring it twice is a 404: it is no longer an active example.
    status, _ = await api.call("DELETE", f"{base}/{created['id']}", "alice")
    assert status == 404


async def test_accepting_is_where_an_imported_metric_becomes_reachable(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """B-085. A definition is matched to a question by name and synonym."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())

    status, accepted = await api.call(
        "POST",
        f"{base}/{proposed[0]['id']}/accept",
        "alice",
        {"required_filters": [], "synonyms": ["what we have on the shelves", "listed value"]},
    )

    assert status == 200
    assert accepted["synonyms"] == ["what we have on the shelves", "listed value"]

    _, active = await api.call("GET", base, "alice")
    assert active[0]["synonyms"] == ["what we have on the shelves", "listed value"]


async def test_accepting_without_saying_keeps_the_words_the_import_found(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Omitting the field is not the same as sending an empty list."""
    await _metric_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"
    _, proposed = await api.call("POST", f"{base}/import", "alice", _import_body())
    imported = proposed[0]["synonyms"]
    assert imported, "the fixture's metric table carries synonyms"

    _, accepted = await api.call(
        "POST", f"{base}/{proposed[0]['id']}/accept", "alice", {"required_filters": []}
    )

    assert accepted["synonyms"] == imported


# --- A filter that is checked and cannot exclude anything (B-171) ---


async def _constant_column_table(customer: CustomerDatabase) -> None:
    """A table with one column that never varies, and one that does."""
    engine = create_async_engine(customer.url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS shipments ("
                    "  id integer PRIMARY KEY, active integer, status text)"
                )
            )
            await connection.execute(text("DELETE FROM shipments"))
            await connection.execute(
                text(
                    "INSERT INTO shipments (id, active, status) VALUES "
                    "(1, 1, 'sent'), (2, 1, 'held'), (3, 1, 'sent'), (4, 1, 'held')"
                )
            )
            await connection.execute(
                text(f"GRANT SELECT ON shipments TO {customer.reader_username}")
            )
    finally:
        await engine.dispose()


async def test_a_filter_that_excludes_nothing_is_reported_as_such(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """B-171, on the route the screen calls."""
    await _constant_column_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    # Discovery alone leaves `distinct_est` null; the profiler is what knows.
    await api.call("POST", f"/v1/orgs/{org_id}/data-sources/{source_id}/profile", "alice")
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"

    status, hollow = await api.call(
        "POST",
        base,
        "alice",
        {
            "name": "active_shipments",
            "description": "Shipments still in play.",
            "required_filters": [
                {"table": "shipments", "column": "active", "op": "eq", "values": ["1"]}
            ],
        },
    )
    assert status == 201, hollow
    # Still enforced — the critic really does check it. That is the distinction.
    assert hollow["binds"] is True

    status, real = await api.call(
        "POST",
        base,
        "alice",
        {
            "name": "sent_shipments",
            "description": "Shipments that went out.",
            "required_filters": [
                {"table": "shipments", "column": "status", "op": "eq", "values": ["sent"]}
            ],
        },
    )
    assert status == 201, real

    status, listed = await api.call("GET", base, "alice")
    assert status == 200
    by_name = {row["name"]: row for row in listed}
    assert by_name["active_shipments"]["excluding_nothing"] == ["shipments.active"]
    # `status` holds two values, so its filter does separate rows.
    assert by_name["sent_shipments"]["excluding_nothing"] == []


async def test_a_filter_on_an_unprofiled_column_is_not_called_hollow(
    api: Api, isolated_customer_database: CustomerDatabase
) -> None:
    """Silence where the profiler has not run."""
    await _constant_column_table(isolated_customer_database)
    org_id, source_id = await _org_with_catalog(api, isolated_customer_database)
    base = f"/v1/orgs/{org_id}/data-sources/{source_id}/definitions"

    await api.call(
        "POST",
        base,
        "alice",
        {
            "name": "active_shipments",
            "description": "Shipments still in play.",
            "required_filters": [
                {"table": "shipments", "column": "active", "op": "eq", "values": ["1"]}
            ],
        },
    )

    _, listed = await api.call("GET", base, "alice")
    assert [row["excluding_nothing"] for row in listed] == [[]]
