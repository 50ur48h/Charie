"""Query builder joins on the shop database (P09.2).

Expected numbers are hand-worked from backend/tests/data/shop_db.sql.
Completed Nov-Dec orders by restaurant: Bella Forno 40 + 60 + 50 + 44 = 194,
Forno North 25 + 35 = 60, Test Kitchen 10 + 12 = 22, Lone Star 33 + 22 + 28
= 83; the four groups add up to 359, so no order counts twice.
"""

import contextlib
import datetime
from decimal import Decimal

from sqlalchemy import create_engine, text

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryRequest,
    build_query,
)
from charie.shared.knowledge.recipe import Recipe
from tests.shop import (
    ITEM_SALES,
    ITEMS_ORDERS,
    NET_SALES_WITH_LABEL,
    ORDERS_RESTAURANTS,
    RESTAURANT_NAME_DIM,
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


def _rule_context() -> BuildContext:
    return BuildContext(
        time_zone="America/Chicago",
        links=[ORDERS_RESTAURANTS],
        required_filters={"shop.restaurants": ["restaurants.is_test = false"]},
    )


def test_test_restaurant_rule_cuts_total_and_splits(shop_db) -> None:
    recipes = {"net_sales": NET_SALES_WITH_LABEL}
    total = build_query("net_sales", recipes, _request(dimensions=[]), _rule_context())
    assert "restaurants.is_test = false" in total.sql
    assert shop_db(total.sql).rows == [(Decimal("337.00"),)]
    split = build_query("net_sales", recipes, _request(), _rule_context())
    result = shop_db(split.sql)
    assert result.rows == [
        ("Bella Forno", Decimal("194.00")),
        ("Forno North", Decimal("60.00")),
        ("Lone Star Tacos", Decimal("83.00")),
    ]
    assert sum(row[1] for row in result.rows) == Decimal("337.00")


@contextlib.contextmanager
def _unmatched_order(db):
    """A $7 completed order with no restaurant; removed afterwards."""
    engine = create_engine(db)
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE shop.orders DISABLE TRIGGER ALL"))
            try:
                conn.execute(
                    text(
                        "INSERT INTO shop.orders (id, restaurant_id, created_at, created_on, "
                        "created_local, status, total_amount, tax_amount, delivery_fee) VALUES "
                        "(13, 999, TIMESTAMPTZ '2025-11-05 12:00:00 America/Chicago', "
                        "DATE '2025-11-05', TIMESTAMP '2025-11-05 12:00:00', "
                        "'completed', 7.00, 0.50, 0.00)"
                    )
                )
            finally:
                conn.execute(text("ALTER TABLE shop.orders ENABLE TRIGGER ALL"))
        yield
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM shop.orders WHERE id = 13"))
        engine.dispose()


def test_unmatched_order_keeps_total_and_gets_empty_group(shop_db, db) -> None:
    with _unmatched_order(db):
        total = build_query(
            "net_sales", {"net_sales": NET_SALES_WITH_LABEL}, _request(dimensions=[]), _context()
        )
        assert shop_db(total.sql).rows == [(Decimal("366.00"),)]
        split = build_query(
            "net_sales", {"net_sales": NET_SALES_WITH_LABEL}, _request(), _context()
        )
        result = shop_db(split.sql)
        assert result.rows == [
            ("Bella Forno", Decimal("194.00")),
            ("Forno North", Decimal("60.00")),
            ("Lone Star Tacos", Decimal("83.00")),
            ("Test Kitchen", Decimal("22.00")),
            (None, Decimal("7.00")),
        ]
        assert sum(row[1] for row in result.rows) == Decimal("366.00")


def test_count_joined_column_skips_unmatched(shop_db, db) -> None:
    recipe = Recipe(
        kind="simple",
        table="shop.orders",
        aggregate="count",
        expression="restaurants.id",
        time_column="orders.created_at",
        time_column_type="timestamptz",
        dimensions=[RESTAURANT_NAME_DIM],
        unit="count",
        steps_in_words=["Count the matched orders.", "Unmatched rows count zero."],
    )
    with _unmatched_order(db):
        split = build_query("ids", {"ids": recipe}, _request(), _context())
        result = shop_db(split.sql)
        assert result.rows == [
            ("Bella Forno", 4),
            ("Forno North", 3),
            ("Lone Star Tacos", 3),
            ("Test Kitchen", 2),
            (None, 0),
        ]
        total = build_query("ids", {"ids": recipe}, _request(dimensions=[]), _context())
        assert shop_db(total.sql).rows == [(12,)]
