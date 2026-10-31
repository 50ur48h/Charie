"""Query builder ratios, top N and overlapping groups (P09.2b)."""

import pytest

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryBuildError,
    QueryRequest,
    TopN,
    build_query,
)
from charie.shared.knowledge.recipe import DimensionDetails, Recipe, RecipeDimension
from tests.shop import (
    AVG_COMPLETED_ORDER_VALUE,
    CHANNEL_DIM,
    CHANNEL_PROOF,
    COMPLETED_COUNT,
    COMPLETED_SHARE,
    EMPTY_COUNT,
    ITEM_SALES,
    ITEMS_ORDERS,
    ITEMS_PER_COMPLETED_ORDER,
    NET_SALES,
    ORDER_COUNT,
    ORDERS_RESTAURANTS,
    SESSION_SPEND,
    SESSIONS_CHANNELS,
    STATUS_DIM,
)


def _request(**overrides) -> QueryRequest:
    data: dict = {
        "period": DateRange(start="2025-11-01", end="2025-12-31"),
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


def _recipes() -> dict:
    return {
        "net_sales": NET_SALES,
        "order_count": ORDER_COUNT,
        "completed_count": COMPLETED_COUNT,
        "empty_count": EMPTY_COUNT,
        "item_sales": ITEM_SALES,
        "items_per_completed_order": ITEMS_PER_COMPLETED_ORDER,
        "completed_share": COMPLETED_SHARE,
        "avg_completed_order_value": AVG_COMPLETED_ORDER_VALUE,
    }


def test_ratio_sides_share_a_unit() -> None:
    percent_denominator = ORDER_COUNT.model_copy(update={"unit": "percent"})
    money_over_percent = AVG_COMPLETED_ORDER_VALUE.model_copy(
        update={"denominator": "percent_denominator"}, deep=True
    )
    with pytest.raises(QueryBuildError, match="share a unit"):
        build_query(
            "avg",
            {**_recipes(), "avg": money_over_percent, "percent_denominator": percent_denominator},
            _request(),
            _context(),
        )


def test_ratio_names_unknown_sides() -> None:
    recipe = ITEMS_PER_COMPLETED_ORDER.model_copy(update={"numerator": "missing"})
    with pytest.raises(QueryBuildError, match="unknown numerator `missing`"):
        build_query("r", {**_recipes(), "r": recipe}, _request(), _context())


def test_ratio_refuses_nested_ratios() -> None:
    recipe = ITEMS_PER_COMPLETED_ORDER.model_copy(update={"numerator": "completed_share"})
    with pytest.raises(QueryBuildError, match="not other ratios"):
        build_query(
            "r",
            {**_recipes(), "r": recipe, "completed_share": COMPLETED_SHARE},
            _request(),
            _context(),
        )


def test_ratio_takes_no_filters_of_its_own() -> None:
    recipe = ITEMS_PER_COMPLETED_ORDER.model_copy(update={"filters": ["1 = 1"]})
    with pytest.raises(QueryBuildError, match="filter each side"):
        build_query("r", {**_recipes(), "r": recipe}, _request(), _context())


def test_ratio_needs_matching_time_columns() -> None:
    other_time = COMPLETED_COUNT.model_copy(update={"time_column": "orders.created_on"})
    recipes = {**_recipes(), "completed_count": other_time}
    with pytest.raises(QueryBuildError, match="same time column"):
        build_query("items_per_completed_order", recipes, _request(), _context())


def test_ratio_total_divides_scalars() -> None:
    built = build_query("items_per_completed_order", _recipes(), _request(), _context())
    assert built.is_ratio
    assert built.dimension_columns == []
    assert "FULL OUTER JOIN" not in built.sql
    assert "CAST((" in built.sql
    assert "NULLIF((" in built.sql
    assert "Zero denominators are null, not zero." in built.proof


def test_ratio_splits_align_on_the_same_splits() -> None:
    built = build_query(
        "items_per_completed_order",
        _recipes(),
        _request(dimensions=["dimension.month"]),
        _context(),
    )
    assert built.dimension_columns == ["month"]
    assert "FULL OUTER JOIN" in built.sql
    assert "ON num.month = den.month" in built.sql
    assert "NULLIF(den.value, 0)" in built.sql
    assert built.sql.count("GROUP BY") == 2
    assert any("before dividing" in line for line in built.proof)


def test_ratio_percent_multiplies_by_100() -> None:
    built = build_query(
        "completed_share", _recipes(), _request(dimensions=["dimension.month"]), _context()
    )
    assert built.is_ratio
    assert "* 100" in built.sql
    assert any("points out of 100" in line for line in built.proof)


def test_ratio_sides_must_split_the_same_way() -> None:
    labelled = COMPLETED_COUNT.model_copy(
        update={
            "dimensions": [
                STATUS_DIM.model_copy(update={"label_expression": "orders.status"}),
            ]
        },
        deep=True,
    )
    recipes = {**_recipes(), "completed_count": labelled}
    with pytest.raises(QueryBuildError, match="split differently"):
        build_query(
            "completed_share",
            recipes,
            _request(dimensions=["dimension.status"]),
            _context(),
        )


def test_ratio_side_missing_a_split_is_refused() -> None:
    with pytest.raises(QueryBuildError, match="can't be split by dimension.week"):
        build_query(
            "completed_share",
            _recipes(),
            _request(dimensions=["dimension.week"]),
            _context(),
        )


def test_top_n_needs_a_positive_count_and_a_split() -> None:
    with pytest.raises(QueryBuildError, match="positive whole number"):
        build_query("order_count", _recipes(), _request(top_n=TopN(n=0)), _context())
    with pytest.raises(QueryBuildError, match="needs a split"):
        build_query("order_count", _recipes(), _request(top_n=TopN(n=2)), _context())


def test_top_n_ranks_after_aggregation() -> None:
    first = build_query(
        "net_sales",
        {"net_sales": NET_SALES},
        _request(dimensions=["dimension.status"], top_n=TopN(n=2)),
        _context(),
    )
    assert "ORDER BY value DESC NULLS LAST, status LIMIT 2" in first.sql
    second = build_query(
        "net_sales",
        {"net_sales": NET_SALES},
        _request(dimensions=["dimension.status"], top_n=TopN(n=2)),
        _context(),
    )
    assert first.sql == second.sql


def test_top_n_breaks_ties_by_split() -> None:
    built = build_query(
        "net_sales",
        {"net_sales": NET_SALES},
        _request(dimensions=["dimension.month", "dimension.status"], top_n=TopN(n=3)),
        _context(),
    )
    assert "ORDER BY value DESC NULLS LAST, month, status LIMIT 3" in built.sql


def test_top_n_on_a_ratio() -> None:
    built = build_query(
        "items_per_completed_order",
        _recipes(),
        _request(dimensions=["dimension.month"], top_n=TopN(n=1)),
        _context(),
    )
    assert "FULL OUTER JOIN" in built.sql
    assert "ORDER BY value DESC NULLS LAST, month LIMIT 1" in built.sql


def _channel_details(**overrides) -> DimensionDetails:
    data: dict = {
        "kind": "attribute",
        "table": "shop.session_channels",
        "column": "channel",
        "unique_with": [CHANNEL_PROOF],
    }
    data.update(overrides)
    return DimensionDetails(**data)


def _overlap_context(**overrides) -> BuildContext:
    return _context(
        links=[SESSIONS_CHANNELS],
        dimension_details={"dimension.channel": _channel_details()},
    )


def _overlap_recipes() -> dict:
    return {"session_spend": SESSION_SPEND}


def test_overlap_dedupes_and_marks_metadata() -> None:
    built = build_query(
        "session_spend",
        _overlap_recipes(),
        _request(dimensions=["dimension.channel"]),
        _overlap_context(),
    )
    assert built.overlapping_dimension == "dimension.channel"
    assert not built.is_ratio
    assert "SELECT DISTINCT" in built.sql
    assert "don't add up to the total" in " ".join(built.proof)


def test_overlap_counts_distinct_base_rows() -> None:
    recipe = SESSION_SPEND.model_copy(
        update={"aggregate": "count_distinct", "expression": "sessions.id"}
    )
    built = build_query(
        "session_spend",
        {"session_spend": recipe},
        _request(dimensions=["dimension.channel"]),
        _overlap_context(),
    )
    assert "COUNT(DISTINCT m)" in built.sql


def test_overlap_refuses_unproven_splits() -> None:
    draught = CHANNEL_PROOF.model_copy(update={"exact": False})
    context = _context(
        links=[SESSIONS_CHANNELS],
        dimension_details={"dimension.channel": _channel_details(unique_with=[draught])},
    )
    with pytest.raises(QueryBuildError, match="isn't exact"):
        build_query(
            "session_spend",
            _overlap_recipes(),
            _request(dimensions=["dimension.channel"]),
            context,
        )


def test_overlap_refuses_a_missing_path() -> None:
    lost = CHANNEL_PROOF.model_copy(update={"link_keys": []})
    context = _context(
        links=[SESSIONS_CHANNELS],
        dimension_details={"dimension.channel": _channel_details(unique_with=[lost])},
    )
    with pytest.raises(QueryBuildError, match="tested path"):
        build_query(
            "session_spend",
            _overlap_recipes(),
            _request(dimensions=["dimension.channel"]),
            context,
        )


def test_overlap_refuses_an_untested_link() -> None:
    untested = SESSIONS_CHANNELS.model_copy(update={"tested": False})
    context = _context(
        links=[untested],
        dimension_details={"dimension.channel": _channel_details()},
    )
    with pytest.raises(QueryBuildError, match="tested link"):
        build_query(
            "session_spend",
            _overlap_recipes(),
            _request(dimensions=["dimension.channel"]),
            context,
        )


def test_overlap_refuses_a_wrong_table_proof() -> None:
    other = CHANNEL_PROOF.model_copy(update={"base_table": "shop.orders"})
    context = _context(
        links=[SESSIONS_CHANNELS],
        dimension_details={"dimension.channel": _channel_details(unique_with=[other])},
    )
    with pytest.raises(QueryBuildError, match="about another table"):
        build_query(
            "session_spend",
            _overlap_recipes(),
            _request(dimensions=["dimension.channel"]),
            context,
        )


def test_overlap_allows_only_one_split() -> None:
    second = RecipeDimension(
        key="dimension.channel2",
        title="Channel again",
        kind="attribute",
        table="shop.session_channels",
        expression="session_channels.channel",
    )
    recipe = SESSION_SPEND.model_copy(update={"dimensions": [CHANNEL_DIM, second]})
    context = _context(
        links=[SESSIONS_CHANNELS],
        dimension_details={
            "dimension.channel": _channel_details(),
            "dimension.channel2": _channel_details(),
        },
    )
    with pytest.raises(QueryBuildError, match="Only one overlapping split"):
        build_query(
            "session_spend",
            {"session_spend": recipe},
            _request(dimensions=["dimension.channel", "dimension.channel2"]),
            context,
        )


def test_overlap_refuses_a_ratio_combo() -> None:
    recipe = Recipe(
        kind="ratio",
        title="Spend share",
        numerator="session_spend",
        denominator="session_spend",
        unit="ratio",
        steps_in_words=["Add up the spend twice.", "Never combine overlap with a ratio."],
    )
    context = _context(
        links=[SESSIONS_CHANNELS],
        dimension_details={"dimension.channel": _channel_details()},
    )
    with pytest.raises(QueryBuildError, match="can't be combined"):
        build_query(
            "spend_share",
            {"spend_share": recipe, "session_spend": SESSION_SPEND},
            _request(dimensions=["dimension.channel"]),
            context,
        )


def test_cross_schema_tables_sharing_a_name_are_refused() -> None:
    archive_orders = ORDERS_RESTAURANTS.model_copy(
        update={"to_table": "archive.orders", "to_column": "id"}
    )
    recipe = SESSION_SPEND.model_copy(
        update={
            "table": "shop.orders",
            "expression": "orders.total_amount",
            "time_column": "orders.created_at",
            "dimensions": [
                RecipeDimension(
                    key="dimension.region",
                    title="Region",
                    kind="attribute",
                    table="archive.orders",
                    expression="orders.region",
                )
            ],
        },
        deep=True,
    )
    context = _context(links=[archive_orders])
    with pytest.raises(QueryBuildError, match="share a name"):
        build_query(
            "spend",
            {"spend": recipe},
            _request(dimensions=["dimension.region"]),
            context,
        )
