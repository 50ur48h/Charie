"""Every SECURITY DEFINER function in the database is one somebody declared."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine

from charie.agent.scheduler import ORPHANABLE

pytestmark = pytest.mark.asyncio

APP_ROLE = "charie_app"

#: The declaration. Every SECURITY DEFINER function this product is allowed to have.
SECURITY_DEFINER_FUNCTIONS: dict[str, str] = {
    "auth_membership_role": (
        "Reads org_memberships before the organization is known. This is the "
        "authorization bootstrap: app.org_id cannot be set until the caller's "
        "membership has been established."
    ),
    "auth_memberships_for_user": (
        "Which organizations a person belongs to spans every organization by "
        "definition, so no single app.org_id can answer it."
    ),
    "auth_invitation_by_token": (
        "The token is all the caller has; the organization is what the lookup "
        "answers. Every write in that flow is org-scoped."
    ),
    "auth_recovery_grant_by_token": (
        "Same shape as an invitation, for the way back in when no Admin can sign in (B-017)."
    ),
    "ops_orphaned_runs": (
        "Runs left hanging by a restart, across every organization. Each is then "
        "transitioned inside its own org's session."
    ),
}


async def _rows(dsn: URL, sql: str) -> list[tuple[object, ...]]:
    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            return [tuple(r) for r in (await connection.execute(text(sql))).all()]
    finally:
        await engine.dispose()


async def _definer_functions(dsn: URL) -> dict[str, tuple[object, ...]]:
    rows = await _rows(
        dsn,
        """
        SELECT p.proname,
               p.prosecdef,
               p.provolatile,
               p.proconfig,
               p.oid::bigint
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prosecdef
        """,
    )
    return {str(r[0]): r for r in rows}


async def test_every_security_definer_function_is_declared(app_database: URL) -> None:
    """The counting. An undeclared function is a bypass nobody reviewed."""
    found = await _definer_functions(app_database)

    undeclared = sorted(set(found) - set(SECURITY_DEFINER_FUNCTIONS))
    assert not undeclared, (
        f"SECURITY DEFINER function(s) {undeclared} exist and are not declared in "
        "SECURITY_DEFINER_FUNCTIONS. Each one runs as the owner and can read past "
        "every RLS policy; add it to the list with the reason it cannot be an "
        "ordinary query, or drop it."
    )


async def test_every_declared_function_exists(app_database: URL) -> None:
    """The other direction. A stale declaration excuses a function nobody has."""
    found = await _definer_functions(app_database)

    missing = sorted(set(SECURITY_DEFINER_FUNCTIONS) - set(found))
    assert not missing, f"declared but absent from the database: {missing}"


async def test_every_definer_function_pins_its_search_path(app_database: URL) -> None:
    """The escalation this whole class of function is famous for."""
    for name, row in (await _definer_functions(app_database)).items():
        raw_config: object = row[3]
        entries = cast("list[object]", raw_config) if isinstance(raw_config, list) else []
        config: list[str] = [str(c) for c in entries]
        pinned = [c for c in config if c.startswith("search_path=")]
        assert pinned, f"{name} is SECURITY DEFINER and does not pin search_path"
        assert "pg_catalog" in str(pinned[0]), (
            f"{name} pins search_path without pg_catalog first, so a caller can "
            f"shadow a built-in operator: {pinned[0]}"
        )


async def test_no_definer_function_is_executable_by_public(app_database: URL) -> None:
    """`PUBLIC` gets EXECUTE by default the moment a function is created."""
    for name, row in (await _definer_functions(app_database)).items():
        # By oid, not by a rendered signature.
        granted = await _rows(
            app_database,
            f"SELECT has_function_privilege('public', {row[4]}::oid, 'EXECUTE')",
        )
        assert granted[0][0] is False, f"{name} is executable by PUBLIC"


async def test_the_application_role_can_execute_each_one(app_database: URL) -> None:
    """The other half: revoking from PUBLIC must not have revoked the point."""
    for name, row in (await _definer_functions(app_database)).items():
        granted = await _rows(
            app_database,
            f"SELECT has_function_privilege('{APP_ROLE}', {row[4]}::oid, 'EXECUTE')",
        )
        assert granted[0][0] is True, f"{APP_ROLE} cannot execute {name}"


async def test_no_definer_function_can_write(app_database: URL) -> None:
    """All five answer questions."""
    for name, row in (await _definer_functions(app_database)).items():
        # `provolatile` is Postgres's internal `"char"`, which asyncpg hands back as bytes.
        raw = row[2]
        volatility = raw.decode() if isinstance(raw, bytes) else str(raw)
        assert volatility in {"s", "i"}, (
            f"{name} is VOLATILE, so it may write. Every declared function is a "
            "lookup; make it STABLE or justify the write in the declaration."
        )


async def test_the_orphan_statuses_match_the_scheduler(app_database: URL) -> None:
    """`ops_orphaned_runs` hard-codes the statuses rather than taking them as a parameter."""
    body = await _rows(
        app_database,
        "SELECT prosrc FROM pg_proc WHERE proname = 'ops_orphaned_runs'",
    )
    source = str(body[0][0])

    for status in ORPHANABLE:
        assert f"'{status}'" in source, (
            f"scheduler.ORPHANABLE contains {status!r} and ops_orphaned_runs does "
            "not look for it, so runs in that state would never be swept"
        )
