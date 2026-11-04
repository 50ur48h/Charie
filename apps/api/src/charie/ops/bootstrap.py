"""Set Charie up on start: migrate, grant the app login, and connect the built-in demo database."""

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


#: The hosted sample database every Charie starts connected to: synthetic data, read-only login.
DEMO_SOURCE = {
    "name": "Food delivery demo",
    "host": "ep-proud-boat-za4d26yl-pooler.c-2.eu-west-2.aws.neon.tech",
    "port": "5432",
    "database": "datamind-db",
    "username": "datamind-db_readonly",
    "password": "TT284Cy_lwnKvLjPUukGWXGXQvN5q31C",
}


def _demo(key: str) -> str:
    """The demo source's setting, unless DEMO_SOURCE_<KEY> overrides it."""
    return _env(f"DEMO_SOURCE_{key.upper()}") or DEMO_SOURCE[key]


async def _has_catalog(org_id: uuid.UUID, data_source_id: uuid.UUID) -> bool:
    from charie.catalog import browse

    try:
        await browse.active_catalog(org_id, data_source_id)
    except browse.NoCatalogError:
        return False
    return True


async def _connect_demo_source(org_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Connect the demo database, prove it read-only, and read its structure once."""
    from charie.catalog import discovery, profiler
    from charie.datasources import service as datasources
    from charie.orgs import service as orgs

    if _env("CHARIE_DEMO_SOURCE") == "0":
        print("bootstrap: demo source turned off; connect a database from Settings")
        return True
    name = _demo("name")
    host, port, database = _demo("host"), int(_demo("port")), _demo("database")
    username, password = _demo("username"), _demo("password")

    existing = {source.name: source for source in await datasources.list_data_sources(org_id)}
    if name in existing:
        # Saved again each start, so a new encryption key or address never strands the demo.
        view = await datasources.update_data_source(
            org_id=org_id,
            actor_user_id=user_id,
            data_source_id=existing[name].id,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )
    else:
        view = await datasources.create_data_source(
            org_id=org_id,
            actor_user_id=user_id,
            name=name,
            engine="pg",
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )
    health = await datasources.test_data_source(
        org_id=org_id, actor_user_id=user_id, data_source_id=view.id
    )
    print(f"bootstrap: {name!r} reachable={health.reachable} read-only={health.readonly_verified}")
    if not health.readonly_verified:
        print(f"bootstrap: demo source refused: {health.detail}", file=sys.stderr)
        return False
    if await _has_catalog(org_id, view.id):
        print(f"bootstrap: {name!r} is ready")
    else:
        found = await discovery.discover(
            org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=None
        )
        print(f"bootstrap: discovery: {found.detail}")
        profiled = await profiler.profile(
            org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=None
        )
        print(f"bootstrap: profiling: {profiled.detail}")
    active = await orgs.active_data_source(org_id)
    if active.data_source_id is None:
        # New chats are about this database without anyone choosing it.
        await orgs.set_active_data_source(
            org_id=org_id, actor_user_id=user_id, data_source_id=view.id
        )
    print(f"bootstrap: {name!r} ready to answer questions")
    return True


def prepare() -> int:
    """Before the app serves: the schema, charie_app's login, and the demo organization."""
    migrated = subprocess.run(["alembic", "upgrade", "head"], check=False)  # noqa: S607
    if migrated.returncode != 0:
        return migrated.returncode
    if asyncio.run(grant_app_login.grant()) != 0:
        return 1
    asyncio.run(_ensure_org_and_user())
    print(f"bootstrap: organization {ORG_NAME!r} ready; anyone who signs in joins it")
    return 0


async def _demo_source() -> bool:
    org_id, user_id = await _ensure_org_and_user()
    return await _connect_demo_source(org_id, user_id)


def demo() -> int:
    """While the app serves: connect the demo database. Minutes the first time, seconds after."""
    return 0 if asyncio.run(_demo_source()) else 1


def main(argv: list[str]) -> int:
    step = argv[1] if len(argv) > 1 else "all"
    if step == "prepare":
        return prepare()
    if step == "demo":
        return demo()
    return prepare() or demo()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
