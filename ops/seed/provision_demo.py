"""Build an organization the product can query, from an empty database."""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import uuid

#: The container mounts the API's source here; nothing else is on the path.
sys.path.insert(0, "/app/src")

#: Stable, so a rerun finds what the last run made rather than creating another.
ORG_NAME = os.environ.get("DEMO_ORG_NAME", "Demo")

#: Not a person. The rows this script writes need an actor.
SETUP_USER_EMAIL = "setup@localhost"

#: Compose service names and container-internal ports.
SOURCES: tuple[dict[str, object], ...] = (
    {
        "name": "Pizza demo",
        "host": "seed-pizza-pg",
        "port": 5432,
        "database": "pizza",
        "username": "pizza_readonly",
        "password_env": "SEED_PIZZA_READONLY_PASSWORD",
        "made_by": "make seed",
    },
)


def _reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    """Can this process open a socket to that address?"""
    connection = socket.socket()
    connection.settimeout(timeout)
    try:
        connection.connect((host, port))
    except OSError:
        return False
    else:
        return True
    finally:
        connection.close()


async def _ensure_org_and_actor(engine: object) -> tuple[uuid.UUID, uuid.UUID]:
    """The organization and the actor its audit rows will name."""
    from sqlalchemy import text

    async with engine.begin() as connection:  # type: ignore[attr-defined]
        org_id = (
            await connection.execute(
                text("SELECT id FROM organizations WHERE name = :n"), {"n": ORG_NAME}
            )
        ).scalar_one_or_none()
        if org_id is None:
            org_id = uuid.uuid4()
            await connection.execute(
                text("INSERT INTO organizations (id, name) VALUES (:i, :n)"),
                {"i": org_id, "n": ORG_NAME},
            )
            print(f"created organization {ORG_NAME!r} -> {org_id}")
        else:
            org_id = uuid.UUID(str(org_id))
            print(f"reusing organization {ORG_NAME!r} -> {org_id}")

        user_id = (
            await connection.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": SETUP_USER_EMAIL}
            )
        ).scalar_one_or_none()
        if user_id is None:
            user_id = uuid.uuid4()
            await connection.execute(
                text(
                    "INSERT INTO users (id, external_subject, email, name) "
                    "VALUES (:i, :s, :e, 'Machine setup')"
                ),
                {"i": user_id, "s": f"setup-{user_id}", "e": SETUP_USER_EMAIL},
            )
        else:
            user_id = uuid.UUID(str(user_id))

        await connection.execute(
            text(
                # (org_id, user_id) is the primary key — no surrogate id.
                "INSERT INTO org_memberships (org_id, user_id, role) "
                "VALUES (:o, :u, 'admin') ON CONFLICT DO NOTHING"
            ),
            {"o": org_id, "u": user_id},
        )

    return uuid.UUID(str(org_id)), uuid.UUID(str(user_id))


async def _report_reachability(org_id: uuid.UUID) -> list[str]:
    """Ask, for every registered source, whether the API can reach its address."""
    from sqlalchemy import text

    from charie.db.engine import build_engine

    problems: list[str] = []
    engine = build_engine()
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT o.id, o.name, d.name, d.host_display FROM data_sources d "
                    "JOIN organizations o ON o.id = d.org_id ORDER BY o.name, d.name"
                )
            )
        ).all()
    await engine.dispose()

    print("\nCan the API reach what is registered?")
    if not rows:
        print("  no data sources on this platform database")
        return problems

    elsewhere = 0
    for row_org_id, org_name, source_name, host_display in rows:
        address = str(host_display).split("/")[0]
        host, _, port = address.rpartition(":")
        try:
            ok = _reachable(host, int(port))
        except ValueError:
            ok = False
        mine = uuid.UUID(str(row_org_id)) == org_id
        mark = "ok " if ok else "NO "
        print(f"  {mark} {org_name} / {source_name}: {host_display}")
        if ok:
            continue
        if mine:
            problems.append(f"{org_name} / {source_name} at {host_display}")
        else:
            elsewhere += 1

    if elsewhere:
        print(
            f"\n  {elsewhere} unreachable source(s) in other organizations. Expected if one of "
            "them is the eval harness's (`make evals.setup`), which registers the host's address "
            "on purpose. Not this command's business, so not a failure."
        )
    return problems


async def main() -> int:
    from charie.catalog import cards, discovery, profiler
    from charie.datasources import service as datasources
    from charie.db.engine import build_engine
    from charie.knowledge import embeddings

    engine = build_engine()
    org_id, user_id = await _ensure_org_and_actor(engine)
    await engine.dispose()

    embedder = embeddings.get_embedder()
    print(f"embedder: {'configured' if embedder is not None else 'none — cards stay lexical'}")

    registered = 0
    for spec in SOURCES:
        name = str(spec["name"])
        host, port = str(spec["host"]), int(spec["port"])  # type: ignore[arg-type]
        print(f"\n--- {name} ({host}:{port}) ---")

        password = os.environ.get(str(spec["password_env"]))
        if not password:
            print(f"  skipped: {spec['password_env']} is not set")
            continue

        # Checked before registering rather than after.
        if not _reachable(host, port):
            print(f"  skipped: nothing is listening — run `{spec['made_by']}` first")
            continue

        existing = {source.name: source for source in await datasources.list_data_sources(org_id)}
        if name in existing:
            view = existing[name]
            print(f"  reusing data source -> {view.id}")
        else:
            view = await datasources.create_data_source(
                org_id=org_id,
                actor_user_id=user_id,
                name=name,
                engine="pg",
                host=host,
                port=port,
                database=str(spec["database"]),
                username=str(spec["username"]),
                password=password,
            )
            print(f"  registered -> {view.id}")

        health = await datasources.test_data_source(
            org_id=org_id, actor_user_id=user_id, data_source_id=view.id
        )
        print(f"  reachable={health.reachable} readonly_verified={health.readonly_verified}")
        if not health.readonly_verified:
            # Discovery refuses an unverified source anyway; failing here says why.
            print(f"  NOT read-only: {health.detail}")
            continue

        found = await discovery.discover(
            org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=embedder
        )
        print(f"  discovery: {found.detail}")
        profiled = await profiler.profile(
            org_id=org_id, actor_user_id=user_id, data_source_id=view.id, embedder=embedder
        )
        print(f"  profiling: {profiled.detail}")
        # Idempotent, so a rerun after a key is configured fills in what the first run could not.
        embedded = await cards.embed_cards(org_id, view.id, embedder=embedder)
        print(f"  embedded {embedded} card(s) in the backfill")
        registered += 1

    if not registered:
        print("\nNo data source was registered. Run `make seed` and try again.")
        return 1

    problems = await _report_reachability(org_id)

    print(f"\nDEMO_ORG_ID={org_id}")
    print(
        "\nSign in at http://localhost:3000. If your account is not a member yet, "
        f"an Admin of {ORG_NAME!r} can invite it from the members screen."
    )
    if problems:
        print(
            f"\nThis organization has sources the API cannot reach, so {ORG_NAME!r} is not"
            " usable yet:"
        )
        for line in problems:
            print(f"  - {line}")
        print("A question asked of one of those fails at the connector (B-115).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
