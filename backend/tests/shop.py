"""The shop fixture's recipes, dimensions and links (P09.1).

Constants the query-builder tests share. Units follow P06.2: percentages
are in points, and every number here is hand-worked from shop_db.sql.
"""

from charie.shared.knowledge.query_builder import JoinLink
from charie.shared.knowledge.recipe import Recipe, RecipeDimension

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
    dimensions=[STATUS_DIM],
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

RECIPES = {"net_sales": NET_SALES, "order_count": ORDER_COUNT}
