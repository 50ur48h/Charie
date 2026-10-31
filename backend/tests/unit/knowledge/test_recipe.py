"""Recipe model and fragment check (P09.1)."""

import pytest
from pydantic import ValidationError

from charie.shared.knowledge.details import check_details
from charie.shared.knowledge.recipe import FragmentInfo, RecipeError, check_fragment


def _simple(**overrides):
    data = {
        "kind": "simple",
        "table": "shop.orders",
        "aggregate": "sum",
        "expression": "orders.total_amount",
        "time_column": "orders.created_at",
        "time_column_type": "timestamptz",
        "steps_in_words": ["Add up the orders.", "Only completed ones count."],
    }
    data.update(overrides)
    return data


def test_simple_recipe_needs_table_aggregate_and_expression() -> None:
    for missing in ("table", "aggregate", "expression", "time_column"):
        data = _simple()
        data.pop(missing)
        with pytest.raises(ValidationError):
            check_details("metric", data)


def test_ratio_recipe_needs_numerator_and_denominator() -> None:
    with pytest.raises(ValidationError):
        check_details("metric", {"kind": "ratio", "numerator": "net_sales"})
    with pytest.raises(ValidationError):
        check_details(
            "metric",
            {
                "kind": "ratio",
                "numerator": "net_sales",
                "denominator": "order_count",
                "table": "shop.orders",
            },
        )
    checked = check_details(
        "metric",
        {
            "kind": "ratio",
            "numerator": "net_sales",
            "denominator": "order_count",
            "unit": "ratio",
            "steps_in_words": ["Divide the two totals.", "Null when nothing was sold."],
        },
    )
    assert checked["numerator"] == "net_sales"


def test_money_needs_three_letter_currency() -> None:
    with pytest.raises(ValidationError):
        check_details("metric", _simple(unit="money"))
    with pytest.raises(ValidationError):
        check_details("metric", _simple(unit="money", currency="USDD"))
    with pytest.raises(ValidationError):
        check_details("metric", _simple(currency="USD"))
    checked = check_details("metric", _simple(unit="money", currency="USD"))
    assert checked["currency"] == "USD"


def test_steps_in_words_are_two_to_six() -> None:
    with pytest.raises(ValidationError):
        check_details("metric", _simple(steps_in_words=["Only one."]))
    checked = check_details("metric", _simple())
    assert len(checked["steps_in_words"]) == 2


def test_star_needs_count() -> None:
    with pytest.raises(ValidationError):
        check_details("metric", _simple(expression="*", aggregate="sum"))
    checked = check_details("metric", _simple(expression="*", aggregate="count"))
    assert checked["aggregate"] == "count"


def test_fragment_check_refuses_subquery_aggregate_and_semicolon() -> None:
    with pytest.raises(RecipeError):
        check_fragment("orders.total_amount + (SELECT SUM(x) FROM t)")
    with pytest.raises(RecipeError):
        check_fragment("SUM(orders.total_amount)")
    with pytest.raises(RecipeError):
        check_fragment("orders.total_amount; DELETE FROM shop.orders")
    with pytest.raises(RecipeError):
        check_fragment("PG_SLEEP(orders.total_amount)")


def test_fragment_check_refuses_unqualified_column() -> None:
    with pytest.raises(RecipeError):
        check_fragment("total_amount + orders.tax_amount")


def test_fragment_check_lists_tables() -> None:
    info = check_fragment("orders.total_amount + orders.tax_amount")
    assert isinstance(info, FragmentInfo)
    assert info.tables == ["orders"]
    assert info.columns == ["orders.tax_amount", "orders.total_amount"]
