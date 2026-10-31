"""Query builder splits, time grains and request filters (P09.1b)."""

import pytest

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryBuildError,
    QueryFilter,
    QueryRequest,
    build_query,
)
from charie.shared.knowledge.recipe import Recipe, RecipeDimension
from charie.shared.safety.catalog import Catalog
from charie.shared.safety.sql_check import check_sql
from tests.shop import NET_SALES, RECIPES


def _request(**overrides) -> QueryRequest:
    data: dict = {
        "period": DateRange(start="2025-11-01", end="2025-12-31"),
        "dimensions": ["dimension.status"],
    }
    data.update(overrides)
    return QueryRequest(**data)


def _context(**overrides) -> BuildContext:
    data: dict = {"time_zone": "America/Chicago"}
    data.update(overrides)
    return BuildContext(**data)


def _id_and_label_recipe() -> Recipe:
    base = NET_SALES.model_dump()
    base["dimensions"] = [
        RecipeDimension(
            key="dimension.restaurant",
            title="Restaurant",
            kind="attribute",
            table="shop.orders",
            expression="orders.restaurant_id",
            label_expression="CAST(orders.restaurant_id AS TEXT)",
        )
    ]
    return Recipe(**base)


def test_split_by_main_table_dimension_groups_by_id_and_label() -> None:
    recipe = _id_and_label_recipe()
    built = build_query(
        "net_sales",
        {"net_sales": recipe},
        _request(dimensions=["dimension.restaurant"]),
        _context(),
    )
    assert built.sql.startswith(
        "SELECT orders.restaurant_id AS restaurant, "
        "CAST(orders.restaurant_id AS TEXT) AS restaurant_label, "
        "SUM(orders.total_amount) AS value FROM shop.orders AS orders WHERE "
    )
    assert "GROUP BY orders.restaurant_id, CAST(orders.restaurant_id AS TEXT)" in built.sql
    assert built.dimension_columns == ["restaurant", "restaurant_label"]
    assert built.columns == ["restaurant", "restaurant_label", "value"]


def test_split_by_month_uses_time_zone() -> None:
    built = build_query("net_sales", RECIPES, _request(dimensions=["dimension.month"]), _context())
    assert built.sql.startswith(
        "SELECT CAST(date_trunc('month', orders.created_at "
        "AT TIME ZONE 'America/Chicago') AS DATE) AS month, "
        "SUM(orders.total_amount) AS value FROM shop.orders AS orders WHERE "
    )
    assert built.dimension_columns == ["month"]


def test_week_can_start_on_sunday() -> None:
    built = build_query(
        "net_sales",
        RECIPES,
        _request(dimensions=["dimension.week"]),
        _context(week_starts="sunday"),
    )
    assert (
        "date_trunc('week', orders.created_at AT TIME ZONE 'America/Chicago' "
        "+ INTERVAL '1 day') - INTERVAL '1 day'" in built.sql
    )
    monday = build_query(
        "net_sales",
        RECIPES,
        _request(dimensions=["dimension.week"]),
        _context(week_starts="monday"),
    )
    assert "INTERVAL" not in monday.sql


def test_dimension_not_in_recipe_is_refused() -> None:
    titled = NET_SALES.model_copy(update={"title": "Net sales"})
    with pytest.raises(QueryBuildError, match='"Net sales" can\'t be split by dimension.city'):
        build_query(
            "net_sales", {"net_sales": titled}, _request(dimensions=["dimension.city"]), _context()
        )


def test_request_filter_escapes_quotes() -> None:
    built = build_query(
        "net_sales",
        RECIPES,
        _request(filters=[QueryFilter(dimension="dimension.status", op="in", values=["o'brien"])]),
        _context(),
    )
    assert "orders.status IN ('o''brien')" in built.sql


def test_time_grain_filter_is_refused() -> None:
    with pytest.raises(
        QueryBuildError, match="Use the period to pick dates, not a filter on month"
    ):
        build_query(
            "net_sales",
            RECIPES,
            _request(
                filters=[QueryFilter(dimension="dimension.month", op="in", values=["2025-11"])]
            ),
            _context(),
        )


def test_every_split_query_passes_sql_check() -> None:
    catalog = Catalog(tables=["shop.orders", "shop.restaurants"])
    requests = [
        _request(),
        _request(dimensions=["dimension.month"]),
        _request(dimensions=["dimension.status", "dimension.month"]),
        _request(
            filters=[QueryFilter(dimension="dimension.status", op="not_in", values=["cancelled"])]
        ),
    ]
    for request in requests:
        built = build_query("net_sales", RECIPES, request, _context())
        report = check_sql(built.sql, catalog)
        assert report.ok, report.reasons


def _day_recipe(column: str, column_type: str) -> Recipe:
    day = RecipeDimension(
        key="dimension.day",
        title="Day",
        kind="time",
        table="shop.orders",
        expression=column,
        grain="day",
    )
    return Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="count",
        expression="*",
        time_column=column,
        time_column_type=column_type,
        dimensions=[day],
        steps_in_words=["Count the orders.", "Split them by day."],
    )


def test_time_split_skips_zone_shift_for_date_and_timestamp() -> None:
    dated = build_query(
        "dated",
        {"dated": _day_recipe("orders.created_on", "date")},
        _request(dimensions=["dimension.day"]),
        _context(),
    )
    assert "date_trunc('day', orders.created_on)" in dated.sql
    assert "AT TIME ZONE" not in dated.sql
    stamped = build_query(
        "stamped",
        {"stamped": _day_recipe("orders.created_local", "timestamp")},
        _request(dimensions=["dimension.day"]),
        _context(),
    )
    assert "date_trunc('day', orders.created_local)" in stamped.sql
    assert "AT TIME ZONE" not in stamped.sql
    zoned = build_query("net_sales", RECIPES, _request(dimensions=["dimension.month"]), _context())
    assert "AT TIME ZONE 'America/Chicago'" in zoned.sql
