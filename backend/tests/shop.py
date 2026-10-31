"""The shop fixture's recipes, dimensions and links (P09.1).

Constants the query-builder tests share. Units follow P06.2: percentages
are in points, and every number here is hand-worked from shop_db.sql.
"""

from charie.shared.knowledge.query_builder import JoinLink
from charie.shared.knowledge.recipe import DimensionProof, Recipe, RecipeDimension

STATUS_DIM = RecipeDimension(
    key="dimension.status",
    title="Status",
    kind="attribute",
    table="shop.orders",
    expression="orders.status",
)

MONTH_DIM = RecipeDimension(
    key="dimension.month",
    title="Month",
    kind="time",
    table="shop.orders",
    expression="orders.created_at",
    grain="month",
)

WEEK_DIM = RecipeDimension(
    key="dimension.week",
    title="Week",
    kind="time",
    table="shop.orders",
    expression="orders.created_at",
    grain="week",
)

NET_SALES = Recipe(
    kind="simple",
    table="shop.orders",
    aggregate="sum",
    expression="orders.total_amount",
    filters=["orders.status = 'completed'"],
    time_column="orders.created_at",
    time_column_type="timestamptz",
    dimensions=[STATUS_DIM, MONTH_DIM, WEEK_DIM],
    unit="money",
    currency="USD",
    steps_in_words=[
        "Add up every completed order total.",
        "Test restaurant orders count unless a hard rule says otherwise.",
    ],
)

ORDER_COUNT = Recipe(
    kind="simple",
    table="shop.orders",
    aggregate="count",
    expression="*",
    filters=[],
    time_column="orders.created_at",
    time_column_type="timestamptz",
    dimensions=[STATUS_DIM, MONTH_DIM],
    unit="count",
    steps_in_words=[
        "Count every order in the period.",
        "Filter by status to keep completed or cancelled ones.",
    ],
)

RESTAURANT_NAME_DIM = RecipeDimension(
    key="dimension.restaurant_name",
    title="Restaurant",
    kind="attribute",
    table="shop.restaurants",
    expression="restaurants.name",
)

NET_SALES_WITH_LABEL = NET_SALES.model_copy(
    update={"dimensions": [RESTAURANT_NAME_DIM]},
    deep=True,
)

ORDERS_RESTAURANTS = JoinLink(
    from_table="shop.orders",
    to_table="shop.restaurants",
    from_column="restaurant_id",
    to_column="id",
    multiplicity="many_to_one",
    tested=True,
    reason="Every order names the restaurant that took it.",
)

ITEMS_ORDERS = JoinLink(
    from_table="shop.order_items",
    to_table="shop.orders",
    from_column="order_id",
    to_column="id",
    multiplicity="many_to_one",
    tested=True,
    reason="Every item belongs to the order it was served with.",
)

RESTAURANTS_CUISINES = JoinLink(
    from_table="shop.restaurants",
    to_table="shop.restaurant_cuisines",
    from_column="id",
    to_column="restaurant_id",
    multiplicity="one_to_many",
    tested=True,
    reason="Restaurant rows list their cuisines.",
)

ITEM_SALES = Recipe(
    kind="simple",
    table="shop.order_items",
    aggregate="sum",
    expression="order_items.quantity",
    time_column="orders.created_at",
    time_column_type="timestamptz",
    dimensions=[MONTH_DIM],
    unit="count",
    steps_in_words=[
        "Add up the ordered item quantities.",
        "Items follow their orders.",
    ],
)

COMPLETED_COUNT = ORDER_COUNT.model_copy(
    update={
        "title": "Completed orders",
        "filters": ["orders.status = 'completed'"],
        "dimensions": [STATUS_DIM, MONTH_DIM],
        "steps_in_words": ["Count every completed order in the period."],
    },
    deep=True,
)

# Matches nothing: the denominator of the zero-denominator ratio proof.
EMPTY_COUNT = ORDER_COUNT.model_copy(
    update={
        "title": "Refunded orders",
        "filters": ["orders.status = 'refunded'"],
        "steps_in_words": ["Count orders with a status no order has."],
    },
    deep=True,
)

ITEMS_PER_COMPLETED_ORDER = Recipe(
    kind="ratio",
    title="Items per completed order",
    numerator="item_sales",
    denominator="completed_count",
    dimensions=[MONTH_DIM],
    unit="ratio",
    steps_in_words=[
        "Add up the quantities and count the completed orders separately.",
        "Divide at the same splits; a missing side stays missing.",
    ],
)

COMPLETED_SHARE = Recipe(
    kind="ratio",
    title="Completed share of orders",
    numerator="completed_count",
    denominator="order_count",
    dimensions=[MONTH_DIM],
    unit="percent",
    steps_in_words=[
        "Count completed orders and all orders separately.",
        "Show the share as points out of 100.",
    ],
)

AVG_COMPLETED_ORDER_VALUE = Recipe(
    kind="ratio",
    title="Average completed order value",
    numerator="net_sales",
    denominator="completed_count",
    unit="money",
    currency="USD",
    steps_in_words=[
        "Add up completed order totals and count the completed orders separately.",
        "Money over a count is money per order.",
    ],
)

CHANNEL_DIM = RecipeDimension(
    key="dimension.channel",
    title="Channel",
    kind="attribute",
    table="shop.session_channels",
    expression="session_channels.channel",
)

CHANNEL_PROOF = DimensionProof(
    base_table="shop.sessions",
    base_key_columns=["id"],
    dimension_expression="session_channels.channel",
    link_keys=["shop.session_channels"],
    checked_at="2025-11-07",
    exact=True,
)

SESSION_SPEND = Recipe(
    kind="simple",
    title="Session spend",
    table="shop.sessions",
    aggregate="sum",
    expression="sessions.amount",
    time_column="sessions.occurred_at",
    time_column_type="timestamptz",
    dimensions=[CHANNEL_DIM],
    unit="money",
    currency="USD",
    steps_in_words=[
        "Add up session spend once per session per channel.",
        "Duplicate bridge rows never double the spend.",
    ],
)

SESSIONS_CHANNELS = JoinLink(
    from_table="shop.sessions",
    to_table="shop.session_channels",
    from_column="id",
    to_column="session_id",
    multiplicity="one_to_many",
    tested=True,
    reason="Channel tags list every channel a session ran on.",
)

RECIPES = {"net_sales": NET_SALES, "order_count": ORDER_COUNT}
