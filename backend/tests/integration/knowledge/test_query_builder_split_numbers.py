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
