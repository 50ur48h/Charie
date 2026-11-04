"""Giving `charie_app` its login in a deployment (WP12.2, B-121)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.asyncpg import dialect as asyncpg_dialect
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

from charie.config import Settings
from charie.db import grant_app_login as module
from charie.db.grant_app_login import ALTER_ROLE_SQL, APP_ROLE, grant

pytestmark = pytest.mark.asyncio


@pytest.fixture
def owner_env(migrated_database: URL, monkeypatch: pytest.MonkeyPatch) -> URL:
    """Point the module's settings at the temp database, the way the job is."""
    resolved = Settings(  # pyright: ignore[reportArgumentType]
        database_url=migrated_database.render_as_string(hide_password=False),
        db_password=None,
    )
    monkeypatch.setattr(module, "get_settings", lambda: resolved)
    return migrated_database


async def _roles_of(dsn: URL) -> dict[str, bool]:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                        "FROM pg_roles WHERE rolname = :r"
                    ),
                    {"r": APP_ROLE},
                )
            ).one_or_none()
    finally:
        await engine.dispose()
    assert row is not None, f"{APP_ROLE} does not exist"
    keys = ("login", "super", "bypassrls", "createdb", "createrole")
    return dict(zip(keys, row, strict=True))


async def _alter(dsn: URL, statement: str) -> None:
    engine = create_async_engine(dsn, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql(statement)
    finally:
        await engine.dispose()


async def test_the_grant_gives_a_login_and_nothing_else(
    owner_env: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The happy path, and the properties the whole tenancy design rests on."""
    monkeypatch.setenv("APP_DB_PASSWORD", f"pw-{uuid.uuid4().hex}")

    assert await grant() == 0

    facts = await _roles_of(owner_env)
    assert facts["login"] is True
    assert facts["super"] is False
    assert facts["bypassrls"] is False
    assert facts["createdb"] is False
    assert facts["createrole"] is False


async def test_the_granted_password_actually_connects(
    owner_env: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proof it is reached: the credential this writes is one asyncpg accepts."""
    password = f"pw-{uuid.uuid4().hex}"
    monkeypatch.setenv("APP_DB_PASSWORD", password)
    assert await grant() == 0

    engine = create_async_engine(owner_env.set(username=APP_ROLE, password=password))
    try:
        async with engine.begin() as connection:
            who = (await connection.execute(text("SELECT current_user"))).scalar_one()
    finally:
        await engine.dispose()
    assert who == APP_ROLE


async def test_a_password_full_of_quotes_survives(
    owner_env: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ALTER ROLE ... PASSWORD` takes a literal, not a placeholder."""
    password = "a'b''c\"d;--" + uuid.uuid4().hex
    monkeypatch.setenv("APP_DB_PASSWORD", password)

    assert await grant() == 0

    engine = create_async_engine(owner_env.set(username=APP_ROLE, password=password))
    try:
        async with engine.begin() as connection:
            assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


async def test_no_password_refuses_rather_than_granting_an_empty_one(
    owner_env: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty password is a role anyone can be."""
    monkeypatch.delenv("APP_DB_PASSWORD", raising=False)

    assert await grant() == 1


async def test_a_role_with_too_much_privilege_stops_the_deploy(
    owner_env: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check that earns this module its place."""
    monkeypatch.setenv("APP_DB_PASSWORD", f"pw-{uuid.uuid4().hex}")
    probe = f"charie_probe_{uuid.uuid4().hex[:12]}"
    await _alter(owner_env, f"CREATE ROLE {probe} WITH BYPASSRLS")
    try:
        assert await grant(role=probe) == 1
    finally:
        await _alter(owner_env, f"DROP ROLE IF EXISTS {probe}")

    # And the real role is untouched by any of it.
    assert (await _roles_of(owner_env))["bypassrls"] is False


async def test_the_real_role_is_never_given_extra_privilege_by_these_tests(
    owner_env: URL,
) -> None:
    """A tripwire, not a tautology."""
    facts = await _roles_of(owner_env)
    assert facts["bypassrls"] is False
    assert facts["super"] is False


# --- The part that needs no database, and would have caught every failure so far ---


@pytest.mark.asyncio(loop_scope="function")
async def test_both_parameters_actually_bind() -> None:
    """Compile the statement and check SQLAlchemy bound what we think it bound."""
    compiled = text(ALTER_ROLE_SQL).compile(dialect=asyncpg_dialect())

    assert set(compiled.params) == {"role", "pw"}
    # Both placeholders reached the driver as positional parameters.
    assert "$1" in str(compiled)
    assert "$2" in str(compiled)
    assert ":role" not in str(compiled)
    assert ":pw" not in str(compiled)
