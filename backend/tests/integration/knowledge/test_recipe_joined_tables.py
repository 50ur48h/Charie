"""Joined recipes validate against the learned catalog (P09.3c fix).

ITEM_SALES lives on shop.order_items but reads its dates from shop.orders
over a tested link. The checks must allow that intermediate join instead
of refusing `shop.orders` as unknown.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from charie.shared.knowledge import questions, recipe_tests, store, versions
from charie.shared.knowledge.query_builder import DateRange, load_build_context
from charie.shared.knowledge.recipe import Recipe


@pytest.fixture()
def practice_shop(db):
    """The practice shop schema with a read-only runner."""
    engine = create_engine(db)
    path = Path(__file__).resolve().parents[2] / "data" / "shop_db.sql"
    code = "\n".join(
        line for line in path.read_text().splitlines() if not line.strip().startswith("--")
    )
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS shop CASCADE"))
        for statement in code.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    def run(sql: str):
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("BEGIN READ ONLY"))
            try:
                result = conn.execute(text(sql))
                return [tuple(row) for row in result.all()]
            finally:
                conn.execute(text("ROLLBACK"))

    yield run
    engine.dispose()


@pytest.fixture()
def version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _seed(db_session, version_id: int) -> None:
    for key, kind, title, details in [
        (
            "table.shop.orders",
            "table",
            "orders",
            {"schema": "shop", "name": "orders", "primary_key": ["id"]},
        ),
        (
            "table.shop.order_items",
            "table",
            "order_items",
            {"schema": "shop", "name": "order_items", "primary_key": ["id"]},
        ),
        (
            "link.shop.order_items.orders",
            "link",
            "items to orders",
            {
                "from_table": "shop.order_items",
                "from_columns": ["order_id"],
                "to_table": "shop.orders",
                "to_columns": ["id"],
                "cardinality": "many_to_one",
                "tested_at": "2026-01-01T00:00:00+00:00",
            },
        ),
        (
            "data_range.shop.order_items",
            "data_range",
            "items range",
            {
                "table": "shop.order_items",
                "date_column": "created_at",
                "date_from": "2025-11-01",
                "date_to": "2025-12-31",
            },
        ),
    ]:
        store.upsert_entry(
            db_session,
            version_id,
            key,
            kind,
            title,
            title,
            details,
            "checked",
            [{"type": "structure", "text": "seed"}],
            "seed",
        )
    store.upsert_entry(
        db_session,
        version_id,
        "metric.item_sales",
        "metric",
        "Item sales",
        "Item sales",
        {
            "kind": "simple",
            "title": "Item sales",
            "table": "shop.order_items",
            "aggregate": "sum",
            "expression": "order_items.quantity",
            "filters": [],
            "time_column": "orders.created_at",
            "time_column_type": "timestamptz",
            "unit": "count",
            "steps_in_words": ["Add up the quantities.", "Keep the kept rows."],
            "dimensions": [],
            "tests": [],
            "reported_checks": [],
            "sql_preview": "seed",
            "tested_at": "2026-01-01T00:00:00+00:00",
        },
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )
    db_session.commit()


def _recipe() -> Recipe:
    return Recipe(
        kind="simple",
        title="Item sales",
        table="shop.order_items",
        aggregate="sum",
        expression="order_items.quantity",
        filters=[],
        time_column="orders.created_at",
        time_column_type="timestamptz",
        unit="count",
        steps_in_words=["Add up the quantities.", "Keep the kept rows."],
        dimensions=[],
    )


def test_joined_total_runs(db_session, version_id, practice_shop) -> None:
    _seed(db_session, version_id)
    context = load_build_context(db_session, version_id, "America/Chicago")
    recipe = _recipe()
    checks, _, _ = recipe_tests.test_recipe(
        recipe,
        "metric.item_sales",
        {"metric.item_sales": recipe},
        DateRange(start="2025-11-01", end="2025-12-31"),
        context,
        practice_shop,
        [],
    )
    by_name = {check.name: check for check in checks}
    assert by_name["runs"].passed is True, by_name["runs"].text
    assert by_name["believable"].passed is True


def test_joined_option_number(db_session, version_id, practice_shop) -> None:
    _seed(db_session, version_id)
    total = questions._metric_total(
        db_session, version_id, "metric.item_sales", practice_shop, "America/Chicago"
    )
    assert total == Decimal(4)
