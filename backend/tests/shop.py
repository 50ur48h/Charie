"""The shop fixture's recipes, dimensions and links (P09.1).

Constants the query-builder tests share. Units follow P06.2: percentages
are in points, and every number here is hand-worked from shop_db.sql.
"""

from charie.shared.knowledge.recipe import Recipe

NET_SALES = Recipe(
    kind="simple",
    table="shop.orders",
    aggregate="sum",
    expression="orders.total_amount",
    filters=["orders.status = 'completed'"],
    time_column="orders.created_at",
    time_column_type="timestamptz",
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
    filters=["orders.status = 'completed'"],
    time_column="orders.created_at",
    time_column_type="timestamptz",
    unit="count",
    steps_in_words=[
        "Count every completed order.",
        "Leave out cancelled orders.",
    ],
)

RECIPES = {"net_sales": NET_SALES, "order_count": ORDER_COUNT}
