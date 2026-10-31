"""Query builder totals over a date range (P09.1)."""

import pytest

from charie.shared.knowledge.query_builder import (
    BuildContext,
    BuiltQuery,
    DateRange,
    QueryBuildError,
    QueryRequest,
    build_query,
)
from charie.shared.knowledge.recipe import Recipe
from charie.shared.safety.catalog import Catalog
from charie.shared.safety.sql_check import check_sql
from tests.shop import RECIPES


def _request(**overrides) -> QueryRequest:
    data: dict = {"period": DateRange(start="2025-11-01", end="2025-11-30")}
    data.update(overrides)
    return QueryRequest(**data)


def _context(**overrides) -> BuildContext:
    data: dict = {"time_zone": "America/Chicago"}
    data.update(overrides)
    return BuildContext(**data)


def test_total_has_aggregate_period_and_filters() -> None:
    built = build_query("net_sales", RECIPES, _request(), _context())
    assert isinstance(built, BuiltQuery)
    assert built.sql == (
        "SELECT SUM(orders.total_amount) AS value FROM shop.orders AS orders "
        "WHERE orders.created_at >= "
        "CAST('2025-11-01 00:00:00 America/Chicago' AS TIMESTAMPTZ) "
        "AND orders.created_at < "
        "CAST('2025-12-01 00:00:00 America/Chicago' AS TIMESTAMPTZ) "
        "AND orders.status = 'completed'"
    )
    assert built.recipe_key == "net_sales"
    assert built.columns == ["value"]
    assert built.dimension_columns == []
    assert built.is_ratio is False
    assert built.overlapping_dimension is None


def test_count_star_and_count_distinct() -> None:
    built = build_query("order_count", RECIPES, _request(), _context())
    assert built.sql.startswith("SELECT COUNT(*) AS value FROM shop.orders AS orders WHERE ")
    distinct = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="count_distinct",
        expression="orders.restaurant_id",
        time_column="orders.created_at",
        time_column_type="timestamptz",
        steps_in_words=["Count the restaurants.", "Only completed orders."],
    )
    built_distinct = build_query("places", {"places": distinct}, _request(), _context())
    assert built_distinct.sql.startswith("SELECT COUNT(DISTINCT orders.restaurant_id) AS value")


def test_period_for_each_time_type() -> None:
    date_recipe = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="sum",
        expression="orders.total_amount",
        time_column="orders.created_on",
        time_column_type="date",
        steps_in_words=["Add up the orders.", "Only completed ones."],
    )
    built = build_query("d", {"d": date_recipe}, _request(), _context())
    assert "CAST('2025-11-01' AS DATE)" in built.sql
    assert "CAST('2025-12-01' AS DATE)" in built.sql
    stamp_recipe = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="sum",
        expression="orders.total_amount",
        time_column="orders.created_local",
        time_column_type="timestamp",
        steps_in_words=["Add up the orders.", "Only completed ones."],
    )
    built_stamp = build_query("t", {"t": stamp_recipe}, _request(), _context())
    assert "CAST('2025-11-01 00:00:00' AS TIMESTAMP)" in built_stamp.sql
    assert "CAST('2025-12-01 00:00:00' AS TIMESTAMP)" in built_stamp.sql


def test_unsupported_requests_are_refused_for_now() -> None:
    joined = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="sum",
        expression="items.price",
        time_column="orders.created_at",
        time_column_type="timestamptz",
        steps_in_words=["Add up the items.", "Only completed orders."],
    )
    with pytest.raises(QueryBuildError, match="needs a join"):
        build_query("j", {"j": joined}, _request(), _context())
    with pytest.raises(QueryBuildError, match="Unknown recipe"):
        build_query("missing", RECIPES, _request(), _context())


def test_every_total_passes_sql_check() -> None:
    catalog = Catalog(tables=["shop.orders", "shop.restaurants"])
    for key in ("net_sales", "order_count"):
        built = build_query(key, RECIPES, _request(), _context())
        report = check_sql(built.sql, catalog)
        assert report.ok, report.reasons


def test_count_column_counts_values_not_sum() -> None:
    counted = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="count",
        expression="orders.id",
        time_column="orders.created_at",
        time_column_type="timestamptz",
        steps_in_words=["Count the orders.", "One row counts once."],
    )
    built = build_query("order_ids", {"order_ids": counted}, _request(), _context())
    assert built.sql.startswith(
        "SELECT COUNT(orders.id) AS value FROM shop.orders AS orders WHERE "
    )
    assert "SUM(" not in built.sql
