"""Uniqueness proofs against the shop database (P09.3b).

Hand-worked numbers come from backend/tests/data/shop_db.sql. Every
order names one restaurant, so splitting by restaurant adds up; session
1 is tagged 'web' twice, so splitting by channel needs deduplication.
"""

from charie.shared.knowledge.dimensions import infer_unique_with
from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryRequest,
    build_query,
)
from charie.shared.knowledge.recipe import DimensionDetails
from tests.shop import (
    CHANNEL_PROOF,
    ITEMS_ORDERS,
    ORDER_COUNT,
    ORDERS_RESTAURANTS,
    RESTAURANT_NAME_DIM,
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


def test_many_to_one(shop_db) -> None:
    proof, info = infer_unique_with(
        lambda sql: shop_db(sql).rows,
        "shop.orders",
        ["id"],
        "shop.restaurants",
        "name",
        [ORDERS_RESTAURANTS],
    )
    assert proof is None
    assert info["reason"] == "no-overlap"
    assert info["pairs"] == info["keys"] == info["total_keys"] == 12
    # A plain split adds up to the total: 6 November and 6 December orders.
    recipe = ORDER_COUNT.model_copy(update={"dimensions": [RESTAURANT_NAME_DIM]})
    built = build_query(
        "order_count",
        {"order_count": recipe},
        _request(dimensions=["dimension.restaurant_name"]),
        _context(),
    )
    assert built.overlapping_dimension is None
    rows = shop_db(built.sql).rows
    assert sum(row[1] for row in rows) == 12
    total = build_query("order_count", {"order_count": recipe}, _request(), _context())
    assert shop_db(total.sql).rows == [(12,)]


def test_overlap_pair(shop_db) -> None:
    proof, info = infer_unique_with(
        lambda sql: shop_db(sql).rows,
        "shop.sessions",
        ["id"],
        "shop.session_channels",
        "channel",
        [SESSIONS_CHANNELS],
    )
    assert proof is not None
    assert proof.exact is True
    assert info["reason"] == "proven"
    assert proof.link_keys == ["shop.session_channels"]
    assert proof.checked_at
    assert (info["pairs"], info["keys"], info["total_keys"]) == (5, 3, 3)
    context = BuildContext(
        time_zone="America/Chicago",
        links=[SESSIONS_CHANNELS],
        dimension_details={
            "dimension.channel": DimensionDetails(
                kind="attribute",
                table="shop.session_channels",
                column="channel",
                unique_with=[proof.model_dump()],
            )
        },
    )
    built = build_query(
        "session_spend",
        {"session_spend": SESSION_SPEND},
        _request(dimensions=["dimension.channel"]),
        context,
    )
    assert built.overlapping_dimension == "dimension.channel"
    # Session 1 is tagged 'web' twice: it counts once, so web is 30.
    assert shop_db(built.sql).rows == [("mail", 40), ("web", 30)]


def test_ambiguous_path_refused(shop_db) -> None:
    detour = ORDERS_RESTAURANTS.model_copy(update={"to_table": "shop.session_channels"})
    hop = ITEMS_ORDERS.model_copy(
        update={"from_table": "shop.sessions", "to_table": "shop.session_channels"}
    )

    def run(sql: str):
        raise AssertionError(f"Ambiguity stops before SQL: {sql}")

    proof, info = infer_unique_with(
        run,
        "shop.sessions",
        ["id"],
        "shop.session_channels",
        "channel",
        [SESSIONS_CHANNELS, detour, hop],
    )
    assert proof is None
    assert info["reason"] == "ambiguous-path"
    assert CHANNEL_PROOF.exact is True
