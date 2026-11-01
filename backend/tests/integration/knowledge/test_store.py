"""Entries and the change log behind Review changes (P07.3)."""

import pytest
from sqlalchemy import select

from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from charie.shared.tables.knowledge import KbChange


def _draft_id(session) -> int:
    return versions.get_or_create_draft(session, "first_learning").id


def _changes(session, version_id: int) -> list:
    return session.scalars(
        select(KbChange).where(KbChange.version_id == version_id).order_by(KbChange.id)
    ).all()


def test_add_change_remove_write_the_change_log(db) -> None:
    with session_scope() as session:
        version_id = _draft_id(session)
        assert (
            store.upsert_entry(
                session,
                version_id,
                "metric.net_sales",
                "metric",
                "Net sales",
                "Sales without delivery fees.",
                {
                    "kind": "simple",
                    "table": "shop.orders",
                    "aggregate": "sum",
                    "expression": "orders.total_amount",
                    "time_column": "orders.created_at",
                    "time_column_type": "timestamptz",
                    "steps_in_words": [
                        "Add up the orders.",
                        "Only completed ones count.",
                    ],
                },
                "guessed",
                [{"type": "query"}],
                "Testing net sales.",
            )
            == "added"
        )
        assert (
            store.upsert_entry(
                session,
                version_id,
                "metric.net_sales",
                "metric",
                "Net sales",
                "Sales without fees or refunds.",
                {
                    "kind": "simple",
                    "table": "shop.orders",
                    "aggregate": "sum",
                    "expression": "orders.net_amount",
                    "time_column": "orders.created_at",
                    "time_column_type": "timestamptz",
                    "steps_in_words": ["Add up the orders.", "Take refunds out of sales."],
                },
                "checked",
                [{"type": "query"}],
                "The refund policy says refunds come out of sales.",
            )
            == "changed"
        )
        assert (
            store.remove_entry(session, version_id, "metric.net_sales", "No such metric.") is True
        )
    with session_scope() as session:
        version_id = versions.get_draft(session).id
        rows = _changes(session, version_id)
        assert [row.change for row in rows] == ["added", "changed", "removed"]
        # P09.9: recipe adds, recipe changes and removals all wait for review.
        assert all(row.is_big is True for row in rows)
        assert rows[0].before is None
        assert rows[0].after["title"] == "Net sales"
        assert rows[1].before["meaning"] == "Sales without delivery fees."
        assert rows[1].after["meaning"] == "Sales without fees or refunds."
        assert rows[2].after is None
        assert rows[2].before["key"] == "metric.net_sales"
        assert store.get_entry(session, version_id, "metric.net_sales") is None


def test_same_entry_twice_is_unchanged(db) -> None:
    with session_scope() as session:
        version_id = _draft_id(session)
        first = store.upsert_entry(
            session,
            version_id,
            "rule.no_test_rows",
            "rule",
            "Leave out test restaurants",
            "Test restaurants skew the numbers.",
            {"rule_type": "exclude_values", "table": "public.restaurants"},
            "guessed",
            [{"type": "owner_notes"}],
            "Reading the notes.",
        )
        assert first == "added"
        again = store.upsert_entry(
            session,
            version_id,
            "rule.no_test_rows",
            "rule",
            "Leave out test restaurants",
            "Test restaurants skew the numbers.",
            {"rule_type": "exclude_values", "table": "public.restaurants"},
            "guessed",
            [{"type": "owner_notes"}],
            "Reading the notes again.",
        )
        assert again == "unchanged"
    with session_scope() as session:
        assert len(_changes(session, versions.get_draft(session).id)) == 1


def test_confirmed_entry_keeps_its_meaning(db) -> None:
    with session_scope() as session:
        version_id = _draft_id(session)
        store.upsert_entry(
            session,
            version_id,
            "metric.net_sales",
            "metric",
            "Net sales",
            "Sales without delivery fees.",
            {
                "kind": "simple",
                "table": "shop.orders",
                "aggregate": "sum",
                "expression": "orders.total_amount",
                "time_column": "orders.created_at",
                "time_column_type": "timestamptz",
                "steps_in_words": ["Add up the orders.", "Only completed ones count."],
            },
            "confirmed",
            [{"type": "owner_approval", "text": "Approved by you"}],
            "Approved.",
        )
        assert (
            store.upsert_entry(
                session,
                version_id,
                "metric.net_sales",
                "metric",
                "NET SALES (learning's words)",
                "Learning's wrong meaning.",
                {
                    "kind": "simple",
                    "table": "shop.orders",
                    "aggregate": "sum",
                    "expression": "orders.net_amount",
                    "time_column": "orders.created_at",
                    "time_column_type": "timestamptz",
                    "steps_in_words": ["Add up the orders.", "Take refunds out of sales."],
                },
                "guessed",
                [{"type": "query"}],
                "Testing net sales.",
            )
            == "changed"
        )
    with session_scope() as session:
        entry = store.get_entry(session, versions.get_draft(session).id, "metric.net_sales")
        assert entry is not None
        assert entry.title == "Net sales"
        assert entry.meaning == "Sales without delivery fees."
        assert entry.confidence == "confirmed"
        assert entry.details["expression"] == "orders.net_amount"
        by_type = {source["type"]: source for source in entry.sources}
        assert by_type["query"]["text"] is None
        assert by_type["owner_approval"]["text"] == "Approved by you"


def test_edit_mark_wrong_and_approve(db) -> None:
    with session_scope() as session:
        version_id = _draft_id(session)
        store.upsert_entry(
            session,
            version_id,
            "style.figures",
            "style",
            "Figures style",
            "Add unaudited figures to profit answers.",
            {"topics": ["profit"]},
            "guessed",
            [{"type": "owner_notes"}],
            "Reading the notes.",
        )
        assert (
            store.edit_entry(session, version_id, "style.figures", title="Profit figures") is True
        )
    with session_scope() as session:
        version_id = versions.get_draft(session).id
        entry = store.get_entry(session, version_id, "style.figures")
        assert entry is not None
        assert (entry.title, entry.confidence) == ("Profit figures", "confirmed")
        by_type = {source["type"]: source for source in entry.sources}
        assert by_type["owner_edit"]["text"] == "Edited by you"
        assert store.approve_entry(session, version_id, "style.figures") is False
        assert store.edit_entry(session, version_id, "style.figures", mark_wrong=True) is True
    with session_scope() as session:
        version_id = versions.get_draft(session).id
        entry = store.get_entry(session, version_id, "style.figures")
        assert entry is not None
        assert entry.confidence == "guessed"
        assert store.approve_entry(session, version_id, "style.figures") is True
        assert store.get_entry(session, version_id, "style.figures").confidence == "confirmed"
        rows = _changes(session, version_id)
        assert [(row.change, row.reason) for row in rows] == [
            ("added", "Reading the notes."),
            ("changed", "Edited by you"),
            ("changed", "Marked as wrong by you"),
            ("changed", "Approved by you"),
        ]
        edited = rows[1]
        assert edited.before["title"] == "Figures style"
        assert edited.after["title"] == "Profit figures"
        assert edited.before["confidence"] == "guessed"
        assert edited.after["confidence"] == "confirmed"


def test_list_filters_by_kind_and_words(db) -> None:
    with session_scope() as session:
        version_id = _draft_id(session)
        store.upsert_entry(
            session,
            version_id,
            "table.public.orders",
            "table",
            "Orders",
            "One row per order.",
            {"schema": "public", "name": "orders"},
            "checked",
            [],
            "Studying the structure.",
        )
        store.upsert_entry(
            session,
            version_id,
            "metric.net_sales",
            "metric",
            "Net sales",
            "Sales without delivery fees.",
            {
                "kind": "simple",
                "table": "shop.orders",
                "aggregate": "sum",
                "expression": "orders.total_amount",
                "time_column": "orders.created_at",
                "time_column_type": "timestamptz",
                "steps_in_words": ["Add up the orders.", "Only completed ones count."],
            },
            "guessed",
            [],
            "Testing net sales.",
        )
        store.upsert_entry(
            session,
            version_id,
            "metric.avg_order",
            "metric",
            "Average order",
            "Net sales divided by the number of orders.",
            {
                "kind": "ratio",
                "numerator": "net_sales",
                "denominator": "order_count",
                "unit": "money",
                "currency": "USD",
                "steps_in_words": ["Divide the totals.", "Null when nothing was sold."],
            },
            "guessed",
            [],
            "Testing averages.",
        )
        by_kind = store.list_entries(session, version_id, kinds=["metric"])
        assert [entry.key for entry in by_kind] == ["metric.avg_order", "metric.net_sales"]
        by_word = store.list_entries(session, version_id, q="delivery FEES")
        assert [entry.key for entry in by_word] == ["metric.net_sales"]
        both_words = store.list_entries(session, version_id, q="orders number")
        assert [entry.key for entry in both_words] == ["metric.avg_order"]
        missing = store.list_entries(session, version_id, q="orders nonexistent")
        assert missing == []


def test_published_versions_reject_writes(db) -> None:
    with session_scope() as session:
        version_id = _draft_id(session)
        store.upsert_entry(
            session,
            version_id,
            "table.public.orders",
            "table",
            "Orders",
            "One row per order.",
            {"schema": "public", "name": "orders"},
            "checked",
            [],
            "Studying the structure.",
        )
        versions.get_draft(session).status = "published"
    with session_scope() as session:
        published_id = versions.get_published(session).id
        with pytest.raises(ValueError, match="draft"):
            store.upsert_entry(
                session,
                published_id,
                "table.public.x",
                "table",
                "X",
                "Y",
                {"schema": "public", "name": "x"},
                "checked",
                [],
                "No.",
            )
        with pytest.raises(ValueError, match="draft"):
            store.remove_entry(session, published_id, "table.public.orders", "No.")
        with pytest.raises(ValueError, match="draft"):
            store.edit_entry(session, published_id, "table.public.orders", title="X")
        with pytest.raises(ValueError, match="draft"):
            store.approve_entry(session, published_id, "table.public.orders")
