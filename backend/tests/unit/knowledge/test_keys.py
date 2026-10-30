"""Knowledge key builders keep database names exactly (P07.3)."""

from charie.shared.knowledge import keys


def test_key_formats() -> None:
    assert keys.table_key("public", "orders") == "table.public.orders"
    assert (
        keys.column_key("public", "orders", "total_amount") == "column.public.orders.total_amount"
    )
    assert (
        keys.link_key("public", "orders", ["restaurant_id"], "public", "restaurants", ["id"])
        == "link.public.orders.restaurant_id~public.restaurants.id"
    )
    assert (
        keys.link_key(
            "public",
            "order_lines",
            ["order_id", "line_no"],
            "public",
            "shipments",
            ["order_id", "line_no"],
        )
        == "link.public.order_lines.order_id+line_no~public.shipments.order_id+line_no"
    )
    assert keys.data_range_key("public", "orders") == "data_range.public.orders"
    assert keys.name_key("public", "restaurants") == "name.public.restaurants"
    assert (
        keys.rule_key("currency", "Money is in US dollars")
        == "rule.currency.money_is_in_us_dollars"
    )
    assert keys.style_key("Add unaudited figures") == "style.add_unaudited_figures"
    assert keys.note_key("how_to", "Investigate a drop!") == "how_to.notes.investigate_a_drop"


def test_slug() -> None:
    assert keys.slug("Money is in US dollars") == "money_is_in_us_dollars"
    assert keys.slug("  spaced   out  ") == "spaced_out"
    assert keys.slug("a+b=c (d)") == "a_b_c_d"
    assert keys.slug("") == "item"
    assert keys.slug("!!!") == "item"
    long_title = "word " * 30
    slug = keys.slug(long_title)
    assert len(slug) <= 60
    assert slug == ("word_" * 12)[:60].rstrip("_")
    assert keys.slug("UPPER CASE") == "upper_case"
