"""Query builder joins on the shop database (P09.2).

Expected numbers are hand-worked from backend/tests/data/shop_db.sql.
Completed Nov-Dec orders by restaurant: Bella Forno 40 + 60 + 50 + 44 = 194,
Forno North 25 + 35 = 60, Test Kitchen 10 + 12 = 22, Lone Star 33 + 22 + 28
= 83; the four groups add up to 359, so no order counts twice.
"""

import datetime
from decimal import Decimal

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryRequest,
    build_query,
)
from tests.shop import (
    ITEM_SALES,
    ITEMS_ORDERS,
    NET_SALES_WITH_LABEL,
    ORDERS_RESTAURANTS,
)


def _request(**overrides) -> QueryRequest:
    data: dict = {
        "period": DateRange(start="2025-11-01", end="2025-12-31"),
        "dimensions": ["dimension.restaurant_name"],
    }
    data.update(overrides)
    return QueryRequest(**data)


def _context() -> BuildContext:
    return BuildContext(time_zone="America/Chicago", links=[ORDERS_RESTAURANTS])


def test_one_join_counts_restaurants_once(shop_db) -> None:
    built = build_query("net_sales", {"net_sales": NET_SALES_WITH_LABEL}, _request(), _context())
    assert built.sql.count("JOIN") == 1
    result = shop_db(built.sql)
    assert result.columns == ["restaurant_name", "value"]
    assert result.rows == [
        ("Bella Forno", Decimal("194.00")),
        ("Forno North", Decimal("60.00")),
        ("Lone Star Tacos", Decimal("83.00")),
        ("Test Kitchen", Decimal("22.00")),
    ]
    assert sum(row[1] for row in result.rows) == Decimal("359.00")


def test_month_split_uses_the_measure_join(shop_db) -> None:
    recipes = {"item_sales": ITEM_SALES}
    request = QueryRequest(
        period=DateRange(start="2025-11-01", end="2025-12-31"),
        dimensions=["dimension.month"],
    )
    context = BuildContext(
        time_zone="America/Chicago",
        links=[ORDERS_RESTAURANTS, ITEMS_ORDERS],
    )
    built = build_query("item_sales", recipes, request, context)
    assert built.sql.count("JOIN") == 1
    result = shop_db(built.sql)
    assert result.rows == [(datetime.date(2025, 11, 1), 3), (datetime.date(2025, 12, 1), 1)]


def test_no_double_count_names_checked_tables(shop_db) -> None:
    built = build_query("net_sales", {"net_sales": NET_SALES_WITH_LABEL}, _request(), _context())
    assert any("shop.orders" in line for line in built.proof)
    assert any("shop.restaurants" in line for line in built.proof)


def test_no_double_count_says_which_link_checks_which_table(shop_db) -> None:
    built = build_query("net_sales", {"net_sales": NET_SALES_WITH_LABEL}, _request(), _context())
    assert any(
        "many_to_one" in line and "orders.restaurant_id" in line and "restaurants.id" in line
        for line in built.proof
    )
    assert any("distinct" in line for line in built.proof)
