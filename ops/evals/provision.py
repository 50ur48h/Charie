"""Build the state the evals need, from nothing (plan WP9.2b)."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

#: Stable, so a rerun finds what the last run made rather than creating another.
ORG_NAME = "evals"

#: The definitions this organization needs to answer its own questions the way its own truths...
EVAL_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "name": "repeat_rate",
        "description": (
            "The proportion of customers who have placed more than one order, out of "
            "customers who have placed at least one. The denominator is customers with "
            "an order — not every customer on file. A customer who has never ordered is "
            "counted in neither half, so compute both halves from the orders table "
            "rather than joining out from customers."
        ),
        "expression": (
            "count(customers with more than one order) / count(customers with at least one order)"
        ),
        "synonyms": ("ordered more than once", "repeat customers", "repeat rate"),
    },
)
SOURCE_NAME = "Demo"
EVAL_USER_EMAIL = "evals@localhost"


async def main() -> int:
    from dotenv import load_dotenv
    from sqlalchemy import text

    from charie.catalog import cards, discovery, profiler
    from charie.datasources import service as datasources
    from charie.db.engine import build_engine
    from charie.knowledge import embeddings
    from charie.semantic import definitions as semantic
    from charie.tenancy.session import org_session

    # The repository's own .env, when there is one.
    if (env := REPO_ROOT / ".env").exists():
        load_dotenv(env)

    host = os.environ.get("SEED_PIZZA_HOST", "localhost")
    port = int(os.environ.get("SEED_PIZZA_PORT", "6543"))
    database = os.environ.get("SEED_PIZZA_DB", "pizza")
    username = os.environ.get("SEED_PIZZA_READONLY_USER", "pizza_readonly")
    password = os.environ.get("SEED_PIZZA_READONLY_PASSWORD")
    if not password:
        raise SystemExit("SEED_PIZZA_READONLY_PASSWORD is not set; `make seed` creates the role.")

    # The organization and its member are written with the owner connection.
    engine = build_engine()
    async with engine.begin() as connection:
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
            print(f"created organization {ORG_NAME} -> {org_id}")
        else:
            org_id = uuid.UUID(str(org_id))
            print(f"reusing organization {ORG_NAME} -> {org_id}")

        user_id = (
            await connection.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": EVAL_USER_EMAIL}
            )
        ).scalar_one_or_none()
        if user_id is None:
            user_id = uuid.uuid4()
            await connection.execute(
                text(
                    "INSERT INTO users (id, external_subject, email, name) "
                    "VALUES (:i, :s, :e, 'Eval harness')"
                ),
                {"i": user_id, "s": f"evals-{user_id}", "e": EVAL_USER_EMAIL},
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
    await engine.dispose()

    existing = {source.name: source for source in await datasources.list_data_sources(org_id)}
    if SOURCE_NAME in existing:
        view = existing[SOURCE_NAME]
        print(f"reusing data source {SOURCE_NAME} -> {view.id}")
    else:
        view = await datasources.create_data_source(
            org_id=org_id,
            actor_user_id=user_id,
            name=SOURCE_NAME,
            engine="pg",
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )
        print(f"registered data source {SOURCE_NAME} -> {view.id}")

    health = await datasources.test_data_source(
        org_id=org_id, actor_user_id=user_id, data_source_id=view.id
    )
    print(f"  reachable={health.reachable} readonly_verified={health.readonly_verified}")
    if not health.readonly_verified:
        # Discovery refuses an unverified source anyway; failing here says why.
        raise SystemExit(f"the credentials were not proven read-only: {health.detail}")

    # Cards are embedded here or nowhere (B-018).
    embedder = embeddings.get_embedder()
    print(f"  embedder: {'configured' if embedder is not None else 'none — cards stay lexical'}")

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
    print(f"  embedded {embedded} card(s)")

    # The definitions this organization has agreed on (B-070).
    known = {definition.name for definition in await semantic.definitions_for(org_id, view.id)}
    for spec in EVAL_DEFINITIONS:
        name = str(spec["name"])
        if name in known:
            print(f"  definition {name}: already defined")
            continue
        await semantic.create(
            org_id=org_id,
            data_source_id=view.id,
            actor_user_id=user_id,
            name=name,
            description=str(spec["description"]),
            expression=str(spec["expression"]),
            synonyms=tuple(spec["synonyms"]),  # type: ignore[arg-type]
        )
        print(f"  definition {name}: created")

    async with org_session(org_id) as session:
        cards = (
            await session.execute(
                text(
                    "SELECT count(*) FROM catalog_tables t JOIN catalog_snapshots s "
                    "ON s.id = t.snapshot_id WHERE s.data_source_id = :d AND s.status = 'active'"
                ),
                {"d": view.id},
            )
        ).scalar_one()
    if not cards:
        raise SystemExit("the catalog is empty; the evals would all fail on grounding")

    print(f"\nEVALS_ORG_ID={org_id}")
    # Say which network this organization is on (B-115).
    print(f"  registered at {host}:{port} — the HOST's address, for this harness")
    if host in {"localhost", "127.0.0.1", "::1"}:
        print("  the api container cannot reach that. For the browser: make demo.setup")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
