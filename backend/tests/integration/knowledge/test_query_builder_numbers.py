"""Query builder numbers on the shop database (P09.1).

Expected numbers are hand-worked from backend/tests/data/shop_db.sql:
completed November orders (Chicago) are 40 + 60 + 25 + 10 + 33 = 168;
December orders are 50 + 22 + 35 + 44 + 28 + 12 = 191; all completed
orders are 168 + 191 = 359. Order 4 is cancelled, so it never counts.
"""

from decimal import Decimal

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryRequest,
    build_query,
)
from charie.shared.knowledge.recipe import Recipe
from tests.shop import RECIPES


def _request(start: str, end: str) -> QueryRequest:
    return QueryRequest(period=DateRange(start=start, end=end))


def _context(time_zone: str) -> BuildContext:
    return BuildContext(time_zone=time_zone)


def test_total_matches_hand_count(shop_db) -> None:
    built = build_query(
        "net_sales", RECIPES, _request("2025-11-01", "2025-12-31"), _context("America/Chicago")
    )
    result = shop_db(built.sql)
    assert result.columns == ["value"]
    assert result.rows[0][0] == Decimal("359.00")


def test_date_range_includes_the_last_evening(shop_db) -> None:
    # The 30 Nov 23:30 order counts in November.
    built = build_query(
        "net_sales", RECIPES, _request("2025-11-01", "2025-11-30"), _context("America/Chicago")
    )
    result = shop_db(built.sql)
    assert result.rows[0][0] == Decimal("168.00")


def test_timestamptz_period_uses_business_time_zone(shop_db) -> None:
    chicago = build_query(
        "net_sales", RECIPES, _request("2025-11-01", "2025-11-30"), _context("America/Chicago")
    )
    assert shop_db(chicago.sql).rows[0][0] == Decimal("168.00")
    # In UTC the 23:30 Chicago order falls on 1 December.
    utc = build_query("net_sales", RECIPES, _request("2025-11-01", "2025-11-30"), _context("UTC"))
    assert shop_db(utc.sql).rows[0][0] == Decimal("135.00")


def test_date_and_timestamp_columns(shop_db) -> None:
    date_recipe = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="sum",
        expression="orders.total_amount",
        filters=["orders.status = 'completed'"],
        time_column="orders.created_on",
        time_column_type="date",
        unit="money",
        currency="USD",
        steps_in_words=["Add up the orders.", "Only completed ones count."],
    )
    stamp_recipe = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="sum",
        expression="orders.total_amount",
        filters=["orders.status = 'completed'"],
        time_column="orders.created_local",
        time_column_type="timestamp",
        unit="money",
        currency="USD",
        steps_in_words=["Add up the orders.", "Only completed ones count."],
    )
    recipes = {"dated": date_recipe, "stamped": stamp_recipe}
    context = _context("America/Chicago")
    dated = build_query("dated", recipes, _request("2025-11-01", "2025-11-30"), context)
    stamped = build_query("stamped", recipes, _request("2025-11-01", "2025-11-30"), context)
    assert shop_db(dated.sql).rows[0][0] == Decimal("168.00")
    assert shop_db(stamped.sql).rows[0][0] == Decimal("168.00")


def test_count_column_counts_orders(shop_db) -> None:
    counted = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="count",
        expression="orders.id",
        time_column="orders.created_at",
        time_column_type="timestamptz",
        steps_in_words=["Count the orders.", "One row counts once."],
    )
    built = build_query(
        "order_ids",
        {"order_ids": counted},
        _request("2025-11-01", "2025-12-31"),
        _context("America/Chicago"),
    )
    # The ids 1 to 12 add up to 78; counting them gives 12.
    assert shop_db(built.sql).rows == [(12,)]
