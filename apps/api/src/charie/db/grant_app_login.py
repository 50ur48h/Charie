"""Give ``charie_app`` its login in a deployed environment (WP12.2)."""

from __future__ import annotations

import asyncio
import os
import sys

from charie.config import get_settings

#: The role migration 0002 creates.
APP_ROLE = "charie_app"

#: The statement builder, as a constant so it can be compiled and asserted without a database.
ALTER_ROLE_SQL = (
    "SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', CAST(:role AS text), CAST(:pw AS text))"
)

#: `grant()` takes the role as an argument purely so its refusal path can be tested against a...


async def grant(role: str = APP_ROLE) -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    # Module-level so a test can substitute it the way the rest of this suite does.
    settings = get_settings()
    password = os.environ.get("APP_DB_PASSWORD", "")
    if not password:
        print(
            "APP_DB_PASSWORD is not set, so charie_app would have no login and "
            "the API could not connect. The deploy seeds it from Key Vault.",
            file=sys.stderr,
        )
        return 1

    # The owner connection.
    engine = create_async_engine(settings.require_database_url(), isolation_level="AUTOCOMMIT")
    try:
        async with engine.begin() as connection:
            # A bound parameter cannot be used here.
            statement = (
                await connection.execute(
                    text(ALTER_ROLE_SQL),
                    {"role": role, "pw": password},
                )
            ).scalar_one()
            await connection.exec_driver_sql(statement)

            # Read back what the role can actually do, exactly as app_role.sql does.
            row = (
                await connection.execute(
                    text(
                        "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
                        "FROM pg_roles WHERE rolname = :r"
                    ),
                    {"r": role},
                )
            ).one()
        can_login, is_super, can_bypass, can_createdb, can_createrole = row
    finally:
        await engine.dispose()

    print(
        f"{role}: login={can_login} superuser={is_super} bypassrls={can_bypass} "
        f"createdb={can_createdb} createrole={can_createrole}"
    )
    if not can_login:
        print(f"{role} still cannot log in.", file=sys.stderr)
        return 1
    if is_super or can_bypass or can_createdb or can_createrole:
        # Refusing here stops the deploy before the API is rolled onto a revision that would...
        print(
            f"{role} has privileges it must not have. The API connects as this "
            "role and RLS is the tenant boundary; refusing to continue.",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    return asyncio.run(grant())


if __name__ == "__main__":
    raise SystemExit(main())
