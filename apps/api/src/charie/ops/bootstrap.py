"""First start of the one-command demo: migrate, grant the app login, connect the demo source."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid

from charie.db import grant_app_login
from charie.orgs.service import demo_org_id

#: The organization everyone joins on sign-in (DEMO_ORG), and the user sign-in suggests.
ORG_NAME = os.environ.get("DEMO_ORG") or "Charie demo"
DEMO_SUBJECT = os.environ.get("DEMO_USER", "demo")


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


async def _ensure_org_and_user() -> tuple[uuid.UUID, uuid.UUID]:
    """The demo organization, and the demo user as its admin. Written with the owner connection."""
    from sqlalchemy import text

    from charie.db.engine import build_engine

    engine = build_engine()
    try:
        async with engine.begin() as connection:
            org_id = demo_org_id(ORG_NAME)
            await connection.execute(
                text("INSERT INTO organizations (id, name) VALUES (:i, :n) ON CONFLICT DO NOTHING"),
                {"i": org_id, "n": ORG_NAME},
            )
            user_id = (
                await connection.execute(
                    text("SELECT id FROM users WHERE external_subject = :s"), {"s": DEMO_SUBJECT}
                )
            ).scalar_one_or_none()
            if user_id is None:
                user_id = uuid.uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO users (id, external_subject, email, name) "
                        "VALUES (:i, :s, :e, :n)"
                    ),
                    {
                        "i": user_id,
                        "s": DEMO_SUBJECT,
                        "e": f"{DEMO_SUBJECT}@example.com",
                        "n": DEMO_SUBJECT.capitalize(),
                    },
                )
            await connection.execute(
                text(
                    "INSERT INTO org_memberships (org_id, user_id, role) "
                    "VALUES (:o, :u, 'admin') ON CONFLICT DO NOTHING"
                ),
                {"o": org_id, "u": user_id},
            )
    finally:
        await engine.dispose()
    return uuid.UUID(str(org_id)), uuid.UUID(str(user_id))


async def _connect_demo_source(org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Register the demo database once, prove it read-only, and build its catalog."""
    from charie.catalog import discovery, profiler
    from charie.datasources import service as datasources
    from charie.orgs import service as orgs

    host = _env("DEMO_SOURCE_HOST")
    password = _env("DEMO_SOURCE_PASSWORD")
    if host is None or password is None:
        print("bootstrap: no demo source configured; connect one from the app")
        return True
    name = _env("DEMO_SOURCE_NAME") or "Demo data"

    existing = {source.name: source for source in await datasources.list_data_sources(org_id)}
    if name in existing:
        print(f"bootstrap: demo source {name!r} already connected")
        return True

    view = await datasources.create_data_source(
        org_id=org_id,
        actor_user_id=user_id,
        name=name,
        engine="pg",
        host=host,
        port=int(_env("DEMO_SOURCE_PORT") or "5432"),
        database=_env("DEMO_SOURCE_DATABASE") or "postgres",
        username=_env("DEMO_SOURCE_USER") or "postgres",
        password=password,
    )
    health = await datasources.test_data_source(
        org_id=org_id, actor_user_id=user_id, data_source_id=view.id
    )
    print(f"bootstrap: {name!r} reachable={health.reachable} read-only={health.readonly_verified}")
    if not health.readonly_verified:
        print(f"bootstrap: demo source refused: {health.detail}", file=sys.stderr)
        return False
    found = await discovery.discover(
        org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=None
    )
    print(f"bootstrap: discovery: {found.detail}")
    profiled = await profiler.profile(
        org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=None
    )
    print(f"bootstrap: profiling: {profiled.detail}")
    # New chats in the demo are about this database without anyone choosing it.
    await orgs.set_active_data_source(org_id=org_id, actor_user_id=user_id, data_source_id=view.id)
    return True


async def _provision() -> bool:
    org_id, user_id = await _ensure_org_and_user()
    print(f"bootstrap: organization {ORG_NAME!r}, sign in as {DEMO_SUBJECT!r}")
    return await _connect_demo_source(org_id, user_id)


def main() -> int:
    migrated = subprocess.run(["alembic", "upgrade", "head"], check=False)  # noqa: S607
    if migrated.returncode != 0:
        return migrated.returncode
    if asyncio.run(grant_app_login.grant()) != 0:
        return 1
    return 0 if asyncio.run(_provision()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
