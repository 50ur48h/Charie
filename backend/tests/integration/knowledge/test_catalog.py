"""The checker's catalog comes from the knowledge entries (P07.5)."""

from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from charie.shared.knowledge.catalog import build_catalog, forbidden_tables
from charie.shared.safety.sql_check import check_sql

TABLE = {"schema": "public", "name": "orders"}
OLD_TABLE = {"schema": "public", "name": "orders_old"}


def _seed() -> int:
    """Two tables and three rules: forbid old, filter status, exclude ids."""
    with session_scope() as session:
        draft = versions.get_or_create_draft(session, "first_learning")
        store.upsert_entry(
            session,
            draft.id,
            "table.public.orders",
            "table",
            "orders",
            "The orders table.",
            TABLE,
            "checked",
            [{"type": "structure", "text": "Read from the database structure"}],
            "seed",
        )
        store.upsert_entry(
            session,
            draft.id,
            "table.public.orders_old",
            "table",
            "orders_old",
            "The old orders table.",
            OLD_TABLE,
            "guessed",
            [{"type": "structure", "text": "Read from the database structure"}],
            "seed",
        )
        store.upsert_entry(
            session,
            draft.id,
            "rule.no_old",
            "rule",
            "Never use orders_old",
            "Never use the table orders_old.",
            {"rule_type": "never_use_table", "table": "public.orders_old"},
            "confirmed",
            [{"type": "owner_notes", "quote": "Never use orders_old"}],
            "seed",
        )
        store.upsert_entry(
            session,
            draft.id,
            "rule.completed_only",
            "rule",
            "Completed orders only",
            "Only completed orders.",
            {
                "rule_type": "always_filter",
                "table": "public.orders",
                "column": "status",
                "values": ["completed"],
            },
            "confirmed",
            [{"type": "owner_notes", "quote": "Completed only"}],
            "seed",
        )
        store.upsert_entry(
            session,
            draft.id,
            "rule.no_tests",
            "rule",
            "Leave out test ids",
            "Leave out test ids.",
            {
                "rule_type": "exclude_values",
                "table": "public.orders",
                "column": "id",
                "values": ["9001", "9002"],
            },
            "confirmed",
            [{"type": "owner_notes", "quote": "Leave out 9001, 9002"}],
            "seed",
        )
        session.commit()
        return draft.id


def _catalog(db):
    with session_scope() as session:
        return build_catalog(session, _seed())


def test_forbidden_table_is_blocked(db) -> None:
    catalog = _catalog(db)
    assert "public.orders" in catalog.tables
    assert "public.orders_old" in catalog.tables
    blocked = check_sql("SELECT count(*) FROM public.orders_old", catalog)
    assert not blocked.ok
    assert any("never to use" in reason for reason in blocked.reasons)
    passing = check_sql(
        "SELECT count(*) FROM public.orders WHERE status = 'completed' AND id NOT IN (9001, 9002)",
        catalog,
    )
    assert passing.ok, passing.reasons


def test_required_filter_is_enforced(db) -> None:
    catalog = _catalog(db)
    assert len(catalog.required_filters) == 2
    missing = check_sql("SELECT count(*) FROM public.orders", catalog)
    assert not missing.ok
    assert any("required filter" in reason for reason in missing.reasons)
    partial = check_sql("SELECT count(*) FROM public.orders WHERE status = 'completed'", catalog)
    assert not partial.ok


def test_forbidden_tables_lists_never_use(db) -> None:
    with session_scope() as session:
        version_id = _seed()
        assert forbidden_tables(session, version_id) == {"public.orders_old"}


def test_unknown_rule_table_is_left_out(db) -> None:
    with session_scope() as session:
        version_id = _seed()
        store.upsert_entry(
            session,
            version_id,
            "rule.no_ghost",
            "rule",
            "Never use ghosts",
            "Never use the ghost table.",
            {"rule_type": "never_use_table", "table": "public.ghosts"},
            "confirmed",
            [{"type": "owner_notes", "quote": "No ghosts"}],
            "seed",
        )
        session.commit()
        catalog = build_catalog(session, version_id)
        assert catalog.forbidden_tables == ["public.orders_old"]
