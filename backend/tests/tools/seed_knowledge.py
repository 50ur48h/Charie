"""Seed a tiny knowledge base to look at: version 1 live, draft 2 (P07.4).

Run from `backend/`: `uv run python -m tests.tools.seed_knowledge`.
It refuses unless `APP_ENV=local` and our database has no versions yet.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from charie.shared.config import get_settings
from charie.shared.db import session_scope
from charie.shared.knowledge import store
from charie.shared.knowledge.versions import get_or_create_draft, get_published
from charie.shared.tables.knowledge import KbVersion

ENTRIES = [
    (
        "table.public.orders",
        "table",
        "orders",
        "A table with about 400K rows and 9 columns. Charie explains it in a later step.",
        {"schema": "public", "name": "orders", "row_estimate": 400000},
        "guessed",
        [{"type": "structure", "text": "Read from the database structure"}],
    ),
    (
        "column.public.orders.total_amount",
        "column",
        "orders.total_amount",
        "A numeric(10,2) column in orders. Charie explains it in a later step.",
        {
            "schema": "public",
            "table": "orders",
            "name": "total_amount",
            "data_type": "numeric(10,2)",
        },
        "guessed",
        [{"type": "profile", "text": "Measured from the data"}],
    ),
    (
        "link.public.orders.restaurant_id",
        "link",
        "orders to restaurants",
        "Each order belongs to one restaurant.",
        {
            "from_table": "public.orders",
            "from_columns": ["restaurant_id"],
            "to_table": "public.restaurants",
            "to_columns": ["id"],
            "found_by": "foreign_key",
            "cardinality": "many_to_one",
        },
        "guessed",
        [{"type": "structure", "text": "Read from the database structure"}],
    ),
    (
        "data_range.public.orders",
        "data_range",
        "Dates in orders",
        "The data in orders goes from 1 Jan 2024 to 31 Dec 2025 (column created_at).",
        {
            "table": "public.orders",
            "date_column": "created_at",
            "date_from": "2024-01-01",
            "date_to": "2025-12-31",
            "exact": True,
            "columns": [],
        },
        "checked",
        [{"type": "query", "text": "Measured the first and last dates"}],
    ),
    (
        "rule.no_orders_old",
        "rule",
        "Never use the table orders_old",
        "Never use the table orders_old.",
        {"rule_type": "never_use_table", "table": "public.orders_old"},
        "confirmed",
        [{"type": "owner_notes", "quote": "Never use the orders_old table."}],
    ),
    (
        "style.profit_note",
        "style",
        "Add the profit note",
        "Add this note: “Illustrative, not audited profit”.",
        {"topics": ["profit"]},
        "confirmed",
        [
            {
                "type": "owner_notes",
                "quote": "Add illustrative, not audited profit to profit answers.",
            }
        ],
    ),
]


def main() -> None:
    """Make version 1 live and a draft version 2 with one changed meaning."""
    if get_settings().app_env != "local":
        raise SystemExit("The seed only runs with APP_ENV=local.")
    with session_scope() as session:
        if session.scalar(select(KbVersion.id).limit(1)) is not None:
            raise SystemExit("Our database already has knowledge versions.")
        first = get_or_create_draft(session, "first_learning")
        for key, kind, title, meaning, details, confidence, sources in ENTRIES:
            store.upsert_entry(
                session,
                first.id,
                key,
                kind,
                title,
                meaning,
                details,
                confidence,
                sources,
                "Seeded for the Knowledge screens",
            )
        first.status = "published"
        first.published_at = datetime.now(UTC)
        session.commit()
        published = get_published(session)
        assert published is not None and published.number == 1
        second = get_or_create_draft(session, "owner_edit")
        store.upsert_entry(
            session,
            second.id,
            "table.public.orders",
            "table",
            "orders",
            "A table with about 400K rows and 9 columns. The seed changed this meaning.",
            {"schema": "public", "name": "orders", "row_estimate": 400000},
            "guessed",
            [{"type": "structure", "text": "Read from the database structure"}],
            "Clearer wording.",
        )
        session.commit()
        print(f"Version 1 is live with {len(ENTRIES)} entries.")
        print(f"Draft version {second.number} has 1 change.")


if __name__ == "__main__":
    main()
