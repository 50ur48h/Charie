"""Ways A and B stay independent: different guidance, no query leaks (P10.7)."""

import json
from types import SimpleNamespace

from charie.chat.analyst.helpers.new_number import (
    _normalized_measure_sql,
    _periods_comparable,
    brief_input,
)
from charie.shared.knowledge.sql_writer import brief_for_way


def _brief() -> dict:
    return {
        "input": brief_input(
            question="How many shop orders are there?",
            scope_table="shop.orders",
            time_column="",
            time_zone="America/Chicago",
            splits=[],
            period_start="2025-12-01",
            period_end="2025-12-31",
            structure="shop.orders(id, created_on).",
        ),
        "catalog": {"tables": ["shop.orders"]},
    }


def test_way_instructions_differ() -> None:
    """Way A and way B get different approach lines."""
    brief = _brief()
    assert brief_for_way(brief, "A")["input"]["way_guidance"] == "Use Way A."
    assert brief_for_way(brief, "B")["input"]["way_guidance"] == "Use Way B."
    assert brief_for_way(brief, "")["input"]["way_guidance"] == ""


def test_way_b_input_has_no_way_a_query() -> None:
    """Way B's brief is built from the task, never from way A's answer."""
    sql_a = "SELECT COUNT(*) AS value FROM shop.orders AS orders"
    guided_b = brief_for_way(_brief(), "B")
    shown = json.dumps(guided_b["input"], sort_keys=True)
    assert sql_a not in shown
    assert "shop.orders(id, created_on)." in shown


def _pair(sql: str) -> tuple:
    written = SimpleNamespace(sql=sql, columns=["value"], rows=[[1]])
    return (written, None, True, (1, 2))


def test_same_measure_modulo_dates_compares() -> None:
    sql_2025 = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2025-12-01'"
    )
    sql_2024 = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    assert _periods_comparable([_pair(sql_2025), _pair(sql_2024)]) is True


def test_different_expression_does_not_compare() -> None:
    cents = (
        "SELECT SUM(o.total_cents) AS value FROM shop.orders o "
        "WHERE o.created_at >= DATE '2025-12-01'"
    )
    dollars = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    assert _periods_comparable([_pair(cents), _pair(dollars)]) is False


def test_different_tables_do_not_compare() -> None:
    lines = (
        "SELECT SUM(l.amount) AS value FROM shop.order_lines l "
        "WHERE l.created_at >= DATE '2025-12-01'"
    )
    orders = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    assert _periods_comparable([_pair(lines), _pair(orders)]) is False


def test_normalization_blanks_dates_only() -> None:
    first = "SELECT SUM(x) AS v FROM t WHERE d >= DATE '2025-12-01'"
    second = "SELECT SUM(x) AS v FROM t WHERE d >= DATE '2024-12-01'"
    assert _normalized_measure_sql(first) == _normalized_measure_sql(second)
    assert _normalized_measure_sql(first) != _normalized_measure_sql("SELECT SUM(y) AS v FROM t")


def test_single_period_compares_trivially() -> None:
    assert _periods_comparable([_pair("SELECT 1")]) is True
