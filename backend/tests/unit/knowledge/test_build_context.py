"""Builder context from knowledge (P09.3, unit)."""

import pytest

from charie.shared.knowledge import versions
from charie.shared.knowledge.query_builder import (
    BuildContext,
    JoinLink,
    build_query,
    load_build_context,
)
from charie.shared.knowledge.recipe import Recipe
from charie.shared.knowledge.store import upsert_entry
from tests.shop import NET_SALES_WITH_LABEL


def _seed(db_session) -> int:
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    upsert_entry(
        db_session,
        version_id,
        "table.shop.orders",
        "table",
        "orders",
        "The orders table.",
        {"schema": "shop", "name": "orders"},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    upsert_entry(
        db_session,
        version_id,
        "table.shop.restaurants",
        "table",
        "restaurants",
        "The restaurants table.",
        {"schema": "shop", "name": "restaurants"},
        "checked",
        [{"type": "structure", "text": "Read from the database structure"}],
        "seed",
    )
    upsert_entry(
        db_session,
        version_id,
        "link.shop.orders.restaurant_id~shop.restaurants.id",
        "link",
        "orders.restaurant_id → restaurants.id",
        "Each order points to one restaurant.",
        {
            "from_table": "shop.orders",
            "to_table": "shop.restaurants",
            "from_columns": ["restaurant_id"],
            "to_columns": ["id"],
            "found_by": "foreign_key",
            "cardinality": "many_to_one",
            "match_share": 1.0,
            "tested_at": "2025-11-07T12:00:00+00:00",
        },
        "checked",
        [{"type": "test", "text": "Tested the join on real rows."}],
        "seed",
    )
    upsert_entry(
        db_session,
        version_id,
        "link.shop.orders.coupon_id~shop.coupons.id",
        "link",
        "orders.coupon_id → coupons.id",
        "A guess, never tested.",
        {
            "from_table": "shop.orders",
            "to_table": "shop.coupons",
            "from_columns": ["coupon_id"],
            "to_columns": ["id"],
            "found_by": "matching_name",
            "cardinality": "many_to_one",
        },
        "guessed",
        [{"type": "test", "text": "Matched by name only."}],
        "seed",
    )
    upsert_entry(
        db_session,
        version_id,
        "link.shop.orders.id~shop.order_items.order_id",
        "link",
        "orders.id → order_items.order_id",
        "One row, one column each way.",
        {
            "from_table": "shop.orders",
            "to_table": "shop.order_items",
            "from_columns": ["id"],
            "to_columns": ["order_id"],
            "found_by": "foreign_key",
            "cardinality": "one_to_one",
            "match_share": 1.0,
            "tested_at": "2025-11-07T12:00:00+00:00",
        },
        "checked",
        [{"type": "test", "text": "Tested the join on real rows."}],
        "seed",
    )
    upsert_entry(
        db_session,
        version_id,
        "link.shop.orders.pair~shop.pairs.a",
        "link",
        "orders.pair → pairs.a",
        "Two columns, tested together.",
        {
            "from_table": "shop.orders",
            "to_table": "shop.pairs",
            "from_columns": ["pair_a", "pair_b"],
            "to_columns": ["a", "b"],
            "found_by": "foreign_key",
            "cardinality": "many_to_one",
            "match_share": 1.0,
            "tested_at": "2025-11-07T12:00:00+00:00",
        },
        "checked",
        [{"type": "test", "text": "Tested the join on real rows."}],
        "seed",
    )
    upsert_entry(
        db_session,
        version_id,
        "rule.no_test_restaurants",
        "rule",
        "No test restaurants",
        "Test restaurants never count unless asked.",
        {
            "rule_type": "always_filter",
            "table": "shop.restaurants",
            "column": "is_test",
            "values": ["false"],
        },
        "confirmed",
        [{"type": "owner_notes", "quote": "Test restaurants never count"}],
        "seed",
    )
    upsert_entry(
        db_session,
        version_id,
        "rule.no_archive",
        "rule",
        "No archive tables",
        "Archive tables are never used.",
        {"rule_type": "never_use_table", "table": "archive"},
        "confirmed",
        [{"type": "owner_notes", "quote": "Archive tables are never used"}],
        "seed",
    )
    db_session.commit()
    return version_id


def test_links_rules(db_session) -> None:
    version_id = _seed(db_session)
    context = load_build_context(db_session, version_id, time_zone="America/Chicago")
    assert context.links == [
        JoinLink(
            from_table="shop.orders",
            to_table="shop.restaurants",
            from_column="restaurant_id",
            to_column="id",
            multiplicity="many_to_one",
            tested=True,
            reason="Each order points to one restaurant.",
        )
    ]
    assert context.required_filters == {"shop.restaurants": ["restaurants.is_test = false"]}
    assert context.forbidden_tables == []
    assert context.time_zone == "America/Chicago"
    # The same knowledge builds the same context.
    assert load_build_context(db_session, version_id) == load_build_context(db_session, version_id)


def test_forbidden(db_session) -> None:
    version_id = _seed(db_session)
    upsert_entry(
        db_session,
        version_id,
        "rule.no_restaurants",
        "rule",
        "No restaurants table",
        "The restaurants table is never used.",
        {"rule_type": "never_use_table", "table": "shop.restaurants"},
        "confirmed",
        [{"type": "owner_notes", "quote": "Never use restaurants"}],
        "seed",
    )
    db_session.commit()
    context = load_build_context(db_session, version_id)
    assert context.forbidden_tables == ["shop.restaurants"]
    assert isinstance(context, BuildContext)
    assert context.required_filters["shop.restaurants"] == ["restaurants.is_test = false"]


def test_dimension_details_loaded(db_session) -> None:
    version_id = _seed(db_session)
    upsert_entry(
        db_session,
        version_id,
        "dimension.status",
        "dimension",
        "dimension.status",
        "Split by shop.orders.status.",
        {
            "kind": "attribute",
            "table": "shop.orders",
            "column": "status",
            "label_column": "",
            "grain": None,
            "unique_with": [],
        },
        "checked",
        [{"type": "ai", "text": "Split checked against learned columns"}],
        "seed",
    )
    db_session.commit()
    context = load_build_context(db_session, version_id)
    assert set(context.dimension_details) == {"dimension.status"}
    assert context.dimension_details["dimension.status"].column == "status"


def test_unchecked_link_ignored(db_session) -> None:
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    upsert_entry(
        db_session,
        version_id,
        "link.shop.orders.coupon_id~shop.coupons.id",
        "link",
        "orders.coupon_id → coupons.id",
        "A guess, never tested.",
        {
            "from_table": "shop.orders",
            "to_table": "shop.coupons",
            "from_columns": ["coupon_id"],
            "to_columns": ["id"],
            "found_by": "matching_name",
            "cardinality": "many_to_one",
        },
        "guessed",
        [{"type": "test", "text": "Matched by name only."}],
        "seed",
    )
    db_session.commit()
    assert load_build_context(db_session, version_id).links == []


def test_loaded_filters_reach_the_query(db_session) -> None:
    from charie.shared.knowledge.query_builder import DateRange, QueryBuildError, QueryRequest

    version_id = _seed(db_session)
    context = load_build_context(db_session, version_id)
    built = build_query(
        "net_sales",
        {"net_sales": NET_SALES_WITH_LABEL},
        QueryRequest(
            period=DateRange(start="2025-11-01", end="2025-12-31"),
            dimensions=["dimension.restaurant_name"],
        ),
        context,
    )
    assert "restaurants.is_test = false" in built.sql
    restaurant_recipe = Recipe(
        kind="simple",
        table="shop.restaurants",
        aggregate="count",
        expression="*",
        time_column="restaurants.id",
        time_column_type="date",
        steps_in_words=["Count restaurants.", "Only real ones."],
    )
    shut = context.model_copy(update={"forbidden_tables": ["shop.restaurants"]})
    with pytest.raises(QueryBuildError, match="outside the tenant's data"):
        build_query(
            "restaurants",
            {"restaurants": restaurant_recipe},
            QueryRequest(period=DateRange(start="2025-11-01", end="2025-12-31")),
            shut,
        )
