"""Query builder ratios, top N and overlapping groups on the shop database.

Expected numbers are hand-worked from backend/tests/data/shop_db.sql.
Quantities live on orders 1, 2 (November) and 7 (December): 2 + 1 + 1 = 4.
Completed orders are all except cancelled order 4: 5 in November, 6 in
December, 11 in total. November has 6 orders, December has 6, 12 in total.
"""

from decimal import Decimal

import pytest

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryRequest,
    TopN,
    build_query,
)
from charie.shared.knowledge.recipe import DimensionDetails
from charie.shared.safety.catalog import Catalog, Link
from charie.shared.safety.sql_check import check_sql
from tests.shop import (
    AVG_COMPLETED_ORDER_VALUE,
    CHANNEL_PROOF,
    COMPLETED_COUNT,
    COMPLETED_SHARE,
    EMPTY_COUNT,
    ITEM_SALES,
    ITEMS_ORDERS,
    ITEMS_PER_COMPLETED_ORDER,
    NET_SALES_WITH_LABEL,
    ORDER_COUNT,
    ORDERS_RESTAURANTS,
    SESSION_SPEND,
    SESSIONS_CHANNELS,
)


def _request(**overrides) -> QueryRequest:
    data: dict = {
        "period": DateRange(start="2025-11-01", end="2025-12-31"),
    }
    data.update(overrides)
    return QueryRequest(**data)


def _context() -> BuildContext:
    return BuildContext(
        time_zone="America/Chicago",
        links=[ORDERS_RESTAURANTS, ITEMS_ORDERS],
    )


def _overlap_context() -> BuildContext:
    return BuildContext(
        time_zone="America/Chicago",
        links=[SESSIONS_CHANNELS],
        dimension_details={
            "dimension.channel": DimensionDetails(
                kind="attribute",
                table="shop.session_channels",
                column="channel",
                unique_with=[CHANNEL_PROOF],
            )
        },
    )


def _recipes() -> dict:
    return {
        "net_sales": NET_SALES_WITH_LABEL,
        "order_count": ORDER_COUNT,
        "completed_count": COMPLETED_COUNT,
        "empty_count": EMPTY_COUNT,
        "item_sales": ITEM_SALES,
        "items_per_completed_order": ITEMS_PER_COMPLETED_ORDER,
        "completed_share": COMPLETED_SHARE,
        "avg_completed_order_value": AVG_COMPLETED_ORDER_VALUE,
        "session_spend": SESSION_SPEND,
    }


def _shop_catalog() -> Catalog:
    def link(join) -> Link:
        if join.multiplicity == "many_to_one":
            return Link(
                one_table=join.to_table,
                one_column=join.to_column,
                many_table=join.from_table,
                many_column=join.from_column,
            )
        return Link(
            one_table=join.from_table,
            one_column=join.from_column,
            many_table=join.to_table,
            many_column=join.to_column,
        )

    return Catalog(
        tables=[
            "shop.orders",
            "shop.restaurants",
            "shop.order_items",
            "shop.sessions",
            "shop.session_channels",
        ],
        links=[
            link(ORDERS_RESTAURANTS),
            link(ITEMS_ORDERS),
            link(SESSIONS_CHANNELS),
        ],
    )


def test_weighted_ratio(shop_db) -> None:
    built = build_query(
        "items_per_completed_order",
        _recipes(),
        _request(dimensions=["dimension.month"]),
        _context(),
    )
    result = shop_db(built.sql)
    assert result.columns == ["month", "value"]
    rows = {row[0].month: float(row[1]) for row in result.rows}
    # November: 3 items over 5 completed orders; December: 1 over 6.
    assert rows[11] == pytest.approx(3 / 5)
    assert rows[12] == pytest.approx(1 / 6)
    total = build_query("items_per_completed_order", _recipes(), _request(), _context())
    (value,) = shop_db(total.sql).rows[0]
    # The weighted total (4 over 11) differs from the average of averages.
    assert float(value) == pytest.approx(4 / 11)
    assert float(value) != pytest.approx((rows[11] + rows[12]) / 2)


def test_zero_denominator(shop_db) -> None:
    recipes = {
        "completed_count": COMPLETED_COUNT,
        "empty_count": EMPTY_COUNT,
        "zero_share": COMPLETED_SHARE.model_copy(
            update={"numerator": "completed_count", "denominator": "empty_count"}
        ),
    }
    built = build_query("zero_share", recipes, _request(), _context())
    assert shop_db(built.sql).rows[0][0] is None
    assert "Zero denominators are null, not zero." in built.proof


def test_percent_ratio(shop_db) -> None:
    built = build_query(
        "completed_share",
        _recipes(),
        _request(dimensions=["dimension.month"]),
        _context(),
    )
    rows = {row[0].month: float(row[1]) for row in shop_db(built.sql).rows}
    assert rows[11] == pytest.approx((5 / 6) * 100)
    assert rows[12] == 100
    total = build_query("completed_share", _recipes(), _request(), _context())
    (value,) = shop_db(total.sql).rows[0]
    assert float(value) == pytest.approx((11 / 12) * 100)


def test_money_over_count_ratio(shop_db) -> None:
    built = build_query("avg_completed_order_value", _recipes(), _request(), _context())
    (value,) = shop_db(built.sql).rows[0]
    assert float(value) == pytest.approx(359 / 11)


def test_top_n_numbers(shop_db) -> None:
    built = build_query(
        "net_sales",
        {"net_sales": NET_SALES_WITH_LABEL},
        _request(dimensions=["dimension.restaurant_name"], top_n=TopN(n=2)),
        _context(),
    )
    assert shop_db(built.sql).rows == [
        ("Bella Forno", Decimal("194.00")),
        ("Lone Star Tacos", Decimal("83.00")),
    ]


def test_bridge_duplicates(shop_db) -> None:
    built = build_query(
        "session_spend",
        {"session_spend": SESSION_SPEND},
        _request(dimensions=["dimension.channel"]),
        _overlap_context(),
    )
    # Session 1 is tagged 'web' twice: naive joins count its 10 twice.
    assert shop_db(built.sql).rows == [
        ("mail", Decimal("40.00")),
        ("web", Decimal("30.00")),
    ]


def test_overlap_note(shop_db) -> None:
    built = build_query(
        "session_spend",
        {"session_spend": SESSION_SPEND},
        _request(dimensions=["dimension.channel"]),
        _overlap_context(),
    )
    assert built.overlapping_dimension == "dimension.channel"
    assert any("don't add up to the total" in line for line in built.proof)
    assert shop_db(built.sql).columns == ["channel", "value"]


def test_all_pass_checker(shop_db) -> None:
    catalog = _shop_catalog()
    queries = [
        build_query("items_per_completed_order", _recipes(), _request(), _context()),
        build_query(
            "items_per_completed_order",
            _recipes(),
            _request(dimensions=["dimension.month"]),
            _context(),
        ),
        build_query(
            "completed_share",
            _recipes(),
            _request(dimensions=["dimension.month"]),
            _context(),
        ),
        build_query(
            "net_sales",
            {"net_sales": NET_SALES_WITH_LABEL},
            _request(dimensions=["dimension.restaurant_name"], top_n=TopN(n=2)),
            _context(),
        ),
        build_query(
            "session_spend",
            {"session_spend": SESSION_SPEND},
            _request(dimensions=["dimension.channel"]),
            _overlap_context(),
        ),
    ]
    for built in queries:
        report = check_sql(built.sql, catalog)
        assert report.ok, (built.sql, report.reasons)
        shop_db(report.sql)
