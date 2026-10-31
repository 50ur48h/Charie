"""Query builder splits and filters on the shop database (P09.1b).

Expected numbers are hand-worked from backend/tests/data/shop_db.sql.
"""

import datetime
from decimal import Decimal

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryFilter,
    QueryRequest,
    build_query,
)
from tests.shop import ORDER_COUNT, RECIPES


def _request(**overrides) -> QueryRequest:
    data: dict = {"period": DateRange(start="2025-11-01", end="2025-12-31")}
    data.update(overrides)
    return QueryRequest(**data)


def _context() -> BuildContext:
    return BuildContext(time_zone="America/Chicago")


def test_split_adds_up_to_total(shop_db) -> None:
    built = build_query("net_sales", RECIPES, _request(dimensions=["dimension.status"]), _context())
    result = shop_db(built.sql)
    assert result.columns == ["status", "value"]
    assert result.rows == [("completed", Decimal("359.00"))]
    assert sum(row[1] for row in result.rows) == Decimal("359.00")


def test_month_split_uses_business_time_zone(shop_db) -> None:
    built = build_query("net_sales", RECIPES, _request(dimensions=["dimension.month"]), _context())
    result = shop_db(built.sql)
    assert result.rows == [
        (datetime.date(2025, 11, 1), Decimal("168.00")),
        (datetime.date(2025, 12, 1), Decimal("191.00")),
    ]


def test_request_filter_keeps_only_chosen_values(shop_db) -> None:
    recipes = {"order_count": ORDER_COUNT}
    cancelled = build_query(
        "order_count",
        recipes,
        _request(
            filters=[QueryFilter(dimension="dimension.status", op="in", values=["cancelled"])]
        ),
        _context(),
    )
    assert shop_db(cancelled.sql).rows == [(1,)]
    completed = build_query(
        "order_count",
        recipes,
        _request(
            filters=[QueryFilter(dimension="dimension.status", op="in", values=["completed"])]
        ),
        _context(),
    )
    assert shop_db(completed.sql).rows == [(11,)]


def test_timestamp_month_split_keeps_late_order_in_november(shop_db) -> None:
    recipe = ORDER_COUNT.model_copy(
        update={
            "time_column": "orders.created_local",
            "time_column_type": "timestamp",
        }
    )
    built = build_query(
        "order_count",
        {"order_count": recipe},
        _request(
            period=DateRange(start="2025-11-01", end="2025-11-30"),
            dimensions=["dimension.month"],
        ),
        _context(),
    )
    # The 30 Nov 23:30 order is a November order in Chicago wall time.
    assert shop_db(built.sql).rows == [(datetime.date(2025, 11, 1), 6)]


def test_date_day_split_ignores_zone_offset(shop_db) -> None:
    from charie.shared.knowledge.recipe import RecipeDimension

    day = RecipeDimension(
        key="dimension.day",
        title="Day",
        kind="time",
        table="shop.orders",
        expression="orders.created_on",
        grain="day",
    )
    recipe = ORDER_COUNT.model_copy(
        update={
            "time_column": "orders.created_on",
            "time_column_type": "date",
            "dimensions": [day],
        }
    )
    context = BuildContext(time_zone="Australia/Sydney")
    built = build_query(
        "order_count",
        {"order_count": recipe},
        _request(
            period=DateRange(start="2025-11-01", end="2025-11-30"),
            dimensions=["dimension.day"],
        ),
        context,
    )
    # Midnight in Sydney is still the same calendar date.
    assert shop_db(built.sql).rows == [
        (datetime.date(2025, 11, 3), 1),
        (datetime.date(2025, 11, 10), 1),
        (datetime.date(2025, 11, 15), 1),
        (datetime.date(2025, 11, 20), 1),
        (datetime.date(2025, 11, 25), 1),
        (datetime.date(2025, 11, 30), 1),
    ]
