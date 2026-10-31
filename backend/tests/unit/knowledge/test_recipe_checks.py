"""Recipe checks: what holds, what fails, and what stays undecided (P09.3c)."""

from decimal import Decimal

import pytest

from charie.learner.steps.recipes import (
    ProposalError,
    RecipeProposal,
    assemble_ratio,
    assemble_simple,
)
from charie.shared.knowledge import recipe_tests
from charie.shared.knowledge.query_builder import BuildContext, DateRange
from charie.shared.knowledge.recipe import Recipe
from charie.shared.knowledge.recipe_tests import parse_reported_numbers


def _context() -> BuildContext:
    return BuildContext(time_zone="America/Chicago")


def _recipe(**overrides) -> Recipe:
    recipe = {
        "kind": "simple",
        "title": "Net sales",
        "table": "shop.orders",
        "aggregate": "sum",
        "expression": "orders.total_amount",
        "filters": [],
        "time_column": "orders.created_at",
        "time_column_type": "timestamptz",
        "unit": "money",
        "currency": "USD",
        "steps_in_words": ["Add up the totals.", "Only completed ones count."],
    }
    recipe.update(overrides)
    return Recipe(**recipe)


def _period() -> DateRange:
    return DateRange(start="2025-11-01", end="2025-12-31")


def _proposal(**overrides) -> RecipeProposal:
    base = {
        "term": "term.net_sales",
        "kind": "simple",
        "table": "shop.orders",
        "aggregate": "sum",
        "expression": "orders.total_amount",
        "filters": [],
        "time_column": "orders.created_at",
        "unit": "money",
        "steps_in_words": ["Add up the totals.", "Only completed ones count."],
    }
    base.update(overrides)
    return RecipeProposal(**base)


def _lookups():
    return (
        {"orders": "shop.orders"},
        {"shop.orders.created_at": {"type": "timestamp with time zone", "table": "shop.orders"}},
        {},
    )


def test_missing_comparison_not_pass() -> None:
    recipe = _recipe()
    checks, matched, _ = recipe_tests.test_recipe(
        recipe,
        "metric.net_sales",
        {"metric.net_sales": recipe},
        _period(),
        _context(),
        lambda sql: [(Decimal("359"),)] if "GROUP BY" not in sql else [("x", Decimal("359"))],
        [],
    )
    by_name = {check.name: check for check in checks}
    assert by_name["runs"].passed is True
    assert by_name["matches_documents"].passed is None
    assert matched == []


def test_precision() -> None:
    (exact,) = parse_reported_numbers(
        [
            {
                "fact_id": "1",
                "topic": "Net sales",
                "statement": "Net sales were $359.00 in November 2025.",
            }
        ]
    )
    assert (exact.amount, exact.places, exact.unit) == (Decimal("359.00"), 2, "money")
    assert (exact.start, exact.end) == ("2025-11-01", "2025-11-30")
    recipe = _recipe()
    reported = [
        {
            "fact_id": "1",
            "topic": "Net sales",
            "statement": "Net sales were $359 in November 2025.",
        }
    ]
    parsed = parse_reported_numbers(reported)
    period = DateRange(start="2025-11-01", end="2025-11-30")
    checks, matched, _ = recipe_tests.test_recipe(
        recipe,
        "metric.net_sales",
        {"metric.net_sales": recipe},
        period,
        _context(),
        lambda sql: [(Decimal("359.40"),)],
        parsed,
    )
    by_name = {check.name: check for check in checks}
    assert by_name["matches_documents"].passed is True
    assert len(matched) == 1
    checks, _, _ = recipe_tests.test_recipe(
        recipe,
        "metric.net_sales",
        {"metric.net_sales": recipe},
        period,
        _context(),
        lambda sql: [(Decimal("360"),)],
        parsed,
    )
    by_name = {check.name: check for check in checks}
    assert by_name["matches_documents"].passed is False


def _term(key: str) -> dict:
    return {"key": key, "name": key.title(), "unit": "money", "dimensions": []}


def test_unknown_columns_fail_before_a_customer_query_runs() -> None:
    tables, columns, dimensions = _lookups()
    with pytest.raises(ProposalError, match="unknown column"):
        assemble_simple(
            _proposal(term="term.x", expression="orders.nope", time_column="orders.created_at"),
            _term("term.x"),
            tables,
            columns,
            dimensions,
        )
    with pytest.raises(ProposalError, match="unusable"):
        assemble_simple(
            _proposal(
                term="term.x",
                expression="orders.id IN (SELECT id FROM shop.orders)",
                time_column="orders.created_at",
            ),
            _term("term.x"),
            tables,
            columns,
            dimensions,
        )


def test_ratio_cycle() -> None:
    simple = _recipe(title="Orders")
    tested = {"term.orders": ("metric.orders", simple)}
    with pytest.raises(ProposalError, match="not a tested recipe"):
        assemble_ratio(
            RecipeProposal(
                term="term.ratio",
                kind="ratio",
                numerator_key="term.missing",
                denominator_key="term.orders",
            ),
            {"key": "term.ratio", "name": "Ratio"},
            tested,
        )
    ratio = Recipe(
        kind="ratio",
        title="Ratio",
        numerator="metric.orders",
        denominator="metric.orders",
        unit="ratio",
        steps_in_words=["Divide.", "Done."],
    )
    with pytest.raises(ProposalError, match="not other ratios"):
        assemble_ratio(
            RecipeProposal(
                term="term.r2",
                kind="ratio",
                numerator_key="term.ratio",
                denominator_key="term.orders",
            ),
            {"key": "term.r2", "name": "R2"},
            {**tested, "term.ratio": ("metric.ratio", ratio)},
        )
    with pytest.raises(ProposalError, match="by itself"):
        assemble_ratio(
            RecipeProposal(
                term="term.orders",
                kind="ratio",
                numerator_key="term.orders",
                denominator_key="term.orders",
            ),
            {"key": "term.orders", "name": "Orders"},
            tested,
        )
