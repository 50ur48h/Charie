"""F1: only a stated subtraction fits a deduction term; title names win (B026 review)."""

from charie.chat.analyst.helpers.compatibility import HOUSE_TERMS, contradicted_recipe


def _meanings() -> dict:
    return {
        "metric.delivered_order_amount": "Total amount for delivered orders.",
        "metric.gross_including": "Total charged, including tax and delivery fees.",
        "metric.true_net": "Sales minus refunds for delivered orders.",
        "metric.operating_expenses": "Simulated monthly overhead amount.",
        "metric.delivered_orders": "Number of delivered orders for an outlet.",
    }


def _units() -> dict:
    return {
        "metric.delivered_order_amount": "money",
        "metric.gross_including": "money",
        "metric.true_net": "money",
        "metric.operating_expenses": "money",
        "metric.delivered_orders": "count",
    }


def _titles() -> dict:
    return {
        "metric.delivered_order_amount": "Delivered order amount",
        "metric.gross_including": "Gross including tax and fees",
        "metric.true_net": "True net sales",
        "metric.operating_expenses": "Operating expenses",
        "metric.delivered_orders": "Delivered orders",
    }


def _check(question, key):
    return contradicted_recipe(question, key, _meanings(), _units(), _titles())


NET_SALES = "How many orders did we have in December 2025, and what were net sales?"
MIXED = "Show net sales and operating expenses"


def test_net_sales_blocks_delivered_amount() -> None:
    """The pilot failure: gross must not answer for net sales."""
    reason = _check(NET_SALES, "metric.delivered_order_amount")
    assert reason is not None
    assert "no subtraction" in reason


def test_including_tax_is_not_a_subtraction() -> None:
    """Review finding: mentioning tax/fees does not prove they were taken away."""
    assert _check(NET_SALES, "metric.gross_including") is not None


def test_stated_subtraction_fits() -> None:
    """A meaning that states minus refunds is compatible."""
    assert _check("What were net sales in December?", "metric.true_net") is None


def test_named_title_wins_for_its_task() -> None:
    """Review finding: the named operating-expenses recipe still runs."""
    assert _check(MIXED, "metric.operating_expenses") is None


def test_unnamed_gross_still_blocked_in_mixed_question() -> None:
    """Scoping is per task: the unnamed gross recipe stays blocked."""
    assert _check(MIXED, "metric.delivered_order_amount") is not None


def test_counts_keep_today_behavior() -> None:
    """A count can never answer a deduction term, so counts are untouched."""
    assert _check(NET_SALES, "metric.delivered_orders") is None


def test_unknown_unit_blocks_nothing() -> None:
    """Without a known money unit the gate stays inert."""
    assert (
        contradicted_recipe("What were net sales in December?", "metric.mystery", {}, {}, {})
        is None
    )


def test_unknown_money_meaning_is_refused() -> None:
    """An unverifiable money meaning cannot justify a deduction term."""
    assert (
        contradicted_recipe(
            "What were net sales in December?",
            "metric.mystery",
            {},
            {"metric.mystery": "money"},
            {},
        )
        is not None
    )


def test_house_term_conflict_stays_unresolved() -> None:
    """The refunds-versus-tax/fees conflict is recorded, not settled."""
    assert HOUSE_TERMS["net sales"]["source"]
    assert "unresolved" in HOUSE_TERMS["net sales"]["conflict"]
