"""Ways A and B stay independent: different guidance, no query leaks (P10.7)."""

import json

from charie.chat.analyst.helpers.new_number import (
    MeasureDef,
    _measure_descriptor,
    _measures_comparable,
    _normalized_measure_sql,
    _period_boundaries,
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


MONEY_CATALOG = {("shop", "orders", "total"): ("money", "USD")}


def _measures(sql_first: str, sql_second: str, catalog: dict, boundaries=()) -> list:
    return [
        _measure_descriptor(sql_first, catalog, boundaries),
        _measure_descriptor(sql_second, catalog, boundaries),
    ]


def _bounds(*days: str) -> set:
    return set(days)


def test_same_measure_modulo_dates_compares() -> None:
    """Same verified money measure across periods compares; dates still blank."""
    sql_2025 = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2025-12-01'"
    )
    sql_2024 = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    assert (
        _measures_comparable(
            _measures(sql_2025, sql_2024, MONEY_CATALOG, _bounds("2025-12-01", "2024-12-01"))
        )
        is True
    )


def test_case_threshold_dates_do_not_compare() -> None:
    """A shifted CASE threshold changes scaling; only boundaries parameterize."""
    new = (
        "SELECT SUM(CASE WHEN DATE '2025-06-01' > DATE '2025-01-01' "
        "THEN o.total ELSE 0 END) AS value "
        "FROM shop.orders o WHERE o.created_at >= DATE '2025-12-01'"
    )
    old = (
        "SELECT SUM(CASE WHEN DATE '2024-06-01' > DATE '2025-01-01' "
        "THEN o.total ELSE 0 END) AS value "
        "FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    assert (
        _measures_comparable(
            _measures(new, old, MONEY_CATALOG, _bounds("2025-12-01", "2024-12-01"))
        )
        is False
    )


def test_unverified_units_do_not_compare() -> None:
    """Same SQL without a catalog entry refuses; equality alone is not proof."""
    sql_2025 = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2025-12-01'"
    )
    sql_2024 = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    assert (
        _measures_comparable(_measures(sql_2025, sql_2024, {}, _bounds("2025-12-01", "2024-12-01")))
        is False
    )


def test_different_expression_does_not_compare() -> None:
    cents = (
        "SELECT SUM(o.total_cents) AS value FROM shop.orders o "
        "WHERE o.created_at >= DATE '2025-12-01'"
    )
    dollars = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    catalog = {
        ("shop", "orders", "total_cents"): ("money", "USD"),
        ("shop", "orders", "total"): ("money", "USD"),
    }
    assert (
        _measures_comparable(
            _measures(cents, dollars, catalog, _bounds("2025-12-01", "2024-12-01"))
        )
        is False
    )


def test_different_tables_do_not_compare() -> None:
    lines = (
        "SELECT SUM(l.amount) AS value FROM shop.order_lines l "
        "WHERE l.created_at >= DATE '2025-12-01'"
    )
    orders = (
        "SELECT SUM(o.total) AS value FROM shop.orders o WHERE o.created_at >= DATE '2024-12-01'"
    )
    catalog = {
        **MONEY_CATALOG,
        ("shop", "order_lines", "amount"): ("money", "USD"),
    }
    assert (
        _measures_comparable(_measures(lines, orders, catalog, _bounds("2025-12-01", "2024-12-01")))
        is False
    )


def test_distinct_units_do_not_compare() -> None:
    """Same expression, conflicting units across periods: no comparison."""
    first = MeasureDef("SELECT SUM(x)", ("s.t",), (("s", "t", "x"),), "sum", "money")
    second = MeasureDef("SELECT SUM(x)", ("s.t",), (("s", "t", "x"),), "sum", "count")
    assert _measures_comparable([first, second]) is False


def test_case_literals_equal_to_boundaries_do_not_compare() -> None:
    """Exact B021 repro: year periods, same money column, CASE scaling differs."""
    from datetime import date
    from types import SimpleNamespace

    periods = [
        SimpleNamespace(start=date(2025, 1, 1), end=date(2025, 12, 31)),
        SimpleNamespace(start=date(2024, 1, 1), end=date(2024, 12, 31)),
    ]
    boundaries = _period_boundaries(periods)
    new = (
        "SELECT SUM(o.total) / CASE WHEN DATE '2025-01-01' >= DATE '2025-01-01' "
        "THEN 100 ELSE 1 END AS value "
        "FROM shop.orders o WHERE o.created_at >= DATE '2025-01-01' "
        "AND o.created_at < DATE '2026-01-01'"
    )
    old = (
        "SELECT SUM(o.total) / CASE WHEN DATE '2024-01-01' >= DATE '2025-01-01' "
        "THEN 100 ELSE 1 END AS value "
        "FROM shop.orders o WHERE o.created_at >= DATE '2024-01-01' "
        "AND o.created_at < DATE '2025-01-01'"
    )
    assert _measures_comparable(_measures(new, old, MONEY_CATALOG, boundaries)) is False


def test_matching_units_need_matching_currency() -> None:
    """Same money unit in another currency is another measure: no comparison."""
    first = MeasureDef("SELECT SUM(x)", ("s.t",), (("s", "t", "x"),), "sum", "money", "USD")
    second = MeasureDef("SELECT SUM(x)", ("s.t",), (("s", "t", "x"),), "sum", "money", "EUR")
    assert _measures_comparable([first, second]) is False


def test_normalization_blanks_boundaries_only() -> None:
    """Only verified period boundaries blank; calculation dates stay literal."""
    first = "SELECT SUM(x) AS v FROM t WHERE d >= DATE '2025-12-01'"
    second = "SELECT SUM(x) AS v FROM t WHERE d >= DATE '2024-12-01'"
    boundaries = {"2025-12-01", "2024-12-01"}
    assert _normalized_measure_sql(first, boundaries) == _normalized_measure_sql(second, boundaries)
    assert _normalized_measure_sql(first, boundaries) != _normalized_measure_sql(
        "SELECT SUM(y) AS v FROM t", boundaries
    )
    assert "2025-12-01" in _normalized_measure_sql(first)
    cased = (
        "SELECT SUM(CASE WHEN DATE '2025-06-01' > DATE '2025-01-01' THEN x ELSE 0 END) AS v FROM t"
    )
    kept = _normalized_measure_sql(cased, boundaries)
    assert "2025-06-01" in kept and "2025-01-01" in kept


def test_single_measure_follows_unit_evidence() -> None:
    # No column refs means the count default (keeps COUNT(*) working); one
    # period alone never drives a change, so the trivial single still passes.
    assert _measures_comparable([_measure_descriptor("SELECT 1", MONEY_CATALOG)]) is True
    assert (
        _measures_comparable(
            [
                _measure_descriptor(
                    "SELECT SUM(o.total) AS value FROM shop.orders o",
                    MONEY_CATALOG,
                )
            ]
        )
        is True
    )
