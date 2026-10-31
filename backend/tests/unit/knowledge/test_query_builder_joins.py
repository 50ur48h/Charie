"""Query builder joins along tested links (P09.2)."""

import pytest

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    JoinBuilder,
    JoinLink,
    QueryBuildError,
    QueryRequest,
    build_query,
    on,
)
from charie.shared.knowledge.recipe import RecipeDimension
from tests.shop import (
    ITEM_SALES,
    ITEMS_ORDERS,
    NET_SALES_WITH_LABEL,
    ORDERS_RESTAURANTS,
    RESTAURANT_NAME_DIM,
    RESTAURANTS_CUISINES,
)

ORDERS_ALIAS = "orders"
RESTAURANTS_ALIAS = "restaurants"


def _request(**overrides) -> QueryRequest:
    data: dict = {
        "period": DateRange(start="2025-11-01", end="2025-12-31"),
        "dimensions": ["dimension.restaurant_name"],
    }
    data.update(overrides)
    return QueryRequest(**data)


def _context(**overrides) -> BuildContext:
    data: dict = {
        "time_zone": "America/Chicago",
        "links": [ORDERS_RESTAURANTS, ITEMS_ORDERS],
    }
    data.update(overrides)
    return BuildContext(**data)


def _recipes():
    return {"net_sales": NET_SALES_WITH_LABEL}


def test_main_join_uses_tested_link() -> None:
    link = ORDERS_RESTAURANTS
    assert on(ORDERS_ALIAS, link, RESTAURANTS_ALIAS) == ("restaurants.id = orders.restaurant_id")
    built = build_query("net_sales", _recipes(), _request(), _context())
    assert (
        "JOIN shop.restaurants AS restaurants ON restaurants.id = orders.restaurant_id" in built.sql
    )
    assert built.sql.count("JOIN") == 1


def test_label_join_follows_main_path() -> None:
    recipe = NET_SALES_WITH_LABEL.model_copy(
        update={
            "dimensions": [
                RecipeDimension(
                    key="dimension.restaurant",
                    title="Restaurant",
                    kind="attribute",
                    table="shop.orders",
                    expression="orders.restaurant_id",
                    label_expression="restaurants.name",
                )
            ]
        },
        deep=True,
    )
    built = build_query(
        "net_sales",
        {"net_sales": recipe},
        _request(dimensions=["dimension.restaurant"]),
        _context(),
    )
    assert "orders.restaurant_id AS restaurant" in built.sql
    assert "restaurants.name AS restaurant_label" in built.sql
    assert built.sql.count("JOIN") == 1


def test_alias_collision_starts_over() -> None:
    builder = JoinBuilder()
    assert builder.add("shop.orders") == "orders"
    assert builder.add("archive.orders") == "table_2"
    assert builder.add("s.t") == "table_3"
    with pytest.raises(QueryBuildError, match="There is already a table called orders"):
        builder.add("shop.orders")


def test_needs_tested_link() -> None:
    untested = ORDERS_RESTAURANTS.model_copy(update={"tested": False})
    with pytest.raises(
        QueryBuildError,
        match="The shop.restaurants table needs a tested link to join on",
    ):
        build_query("net_sales", _recipes(), _request(), _context(links=[untested]))


def test_two_step_join_follows_tested_links() -> None:
    recipe = ITEM_SALES.model_copy(update={"dimensions": [RESTAURANT_NAME_DIM]}, deep=True)
    built = build_query(
        "item_sales",
        {"item_sales": recipe},
        _request(dimensions=["dimension.restaurant_name"]),
        _context(links=[ORDERS_RESTAURANTS, ITEMS_ORDERS]),
    )
    assert built.sql.count("LEFT JOIN") == 2
    assert (
        "LEFT JOIN shop.orders AS orders ON orders.id = order_items.order_id "
        "LEFT JOIN shop.restaurants AS restaurants ON restaurants.id = orders.restaurant_id"
        in built.sql
    )


def test_equal_paths_prefer_first_link_keys() -> None:
    via_a = JoinLink(
        from_table="shop.orders",
        to_table="shop.a_places",
        from_column="a_id",
        to_column="id",
        multiplicity="many_to_one",
        tested=True,
    )
    a_town = JoinLink(
        from_table="shop.a_places",
        to_table="shop.towns",
        from_column="town_id",
        to_column="id",
        multiplicity="many_to_one",
        tested=True,
    )
    via_b = JoinLink(
        from_table="shop.orders",
        to_table="shop.b_places",
        from_column="b_id",
        to_column="id",
        multiplicity="many_to_one",
        tested=True,
    )
    b_town = JoinLink(
        from_table="shop.b_places",
        to_table="shop.towns",
        from_column="town_id",
        to_column="id",
        multiplicity="many_to_one",
        tested=True,
    )
    recipe = NET_SALES_WITH_LABEL.model_copy(
        update={
            "dimensions": [
                RecipeDimension(
                    key="dimension.town",
                    title="Town",
                    kind="attribute",
                    table="shop.towns",
                    expression="towns.name",
                )
            ]
        },
        deep=True,
    )
    built = build_query(
        "net_sales",
        {"net_sales": recipe},
        _request(dimensions=["dimension.town"]),
        _context(links=[via_b, b_town, via_a, a_town]),
    )
    assert "LEFT JOIN shop.a_places AS a_places" in built.sql
    assert "shop.b_places" not in built.sql


def test_fan_out_dimension_is_refused() -> None:
    recipe = NET_SALES_WITH_LABEL.model_copy(
        update={
            "dimensions": [
                RecipeDimension(
                    key="dimension.cuisine",
                    title="Cuisine",
                    kind="attribute",
                    table="shop.restaurant_cuisines",
                    expression="restaurant_cuisines.cuisine_id",
                )
            ]
        },
        deep=True,
    )
    with pytest.raises(QueryBuildError, match="would count some rows more than once"):
        build_query(
            "net_sales",
            {"net_sales": recipe},
            _request(dimensions=["dimension.cuisine"]),
            _context(links=[ORDERS_RESTAURANTS, RESTAURANTS_CUISINES]),
        )


def test_unreachable_rule_is_refused_not_skipped() -> None:
    with pytest.raises(QueryBuildError, match="Can't enforce the hard rule"):
        build_query(
            "net_sales",
            _recipes(),
            _request(dimensions=[]),
            _context(required_filters={"shop.coupons": ["coupons.code <> 'TEST'"]}),
        )


def test_table_outside_tenant_is_refused() -> None:
    with pytest.raises(QueryBuildError, match="The shop.orders table is outside the tenant's data"):
        build_query("net_sales", _recipes(), _request(), _context(forbidden_tables=["shop.orders"]))


def test_dimensions_cant_select_shop_tables() -> None:
    recipe = NET_SALES_WITH_LABEL.model_copy(
        update={
            "dimensions": [
                RecipeDimension(
                    key="dimension.version",
                    title="Version",
                    kind="attribute",
                    table="shop.migrations",
                    expression="migrations.version",
                )
            ]
        },
        deep=True,
    )
    with pytest.raises(QueryBuildError, match="system table"):
        build_query(
            "net_sales",
            {"net_sales": recipe},
            _request(dimensions=["dimension.version"]),
            _context(),
        )


def test_splits_use_left_join() -> None:
    built = build_query("net_sales", _recipes(), _request(), _context())
    assert (
        "LEFT JOIN shop.restaurants AS restaurants ON restaurants.id = orders.restaurant_id"
        in built.sql
    )


def test_hard_rule_table_is_joined_for_total() -> None:
    built = build_query(
        "net_sales",
        _recipes(),
        _request(dimensions=[]),
        _context(required_filters={"shop.restaurants": ["restaurants.is_test = false"]}),
    )
    assert (
        "LEFT JOIN shop.restaurants AS restaurants ON restaurants.id = orders.restaurant_id"
        in built.sql
    )
    assert "restaurants.is_test = false" in built.sql
