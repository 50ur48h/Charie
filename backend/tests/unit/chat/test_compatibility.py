"""F1: a money recipe whose meaning drops a documented deduction never runs (B020)."""

from charie.chat.analyst.helpers.compatibility import HOUSE_TERMS, contradicted_recipe


def _meanings() -> dict:
    return {
        "metric.delivered_order_amount": "Total amount for delivered orders.",
        "metric.delivered_orders": "Number of delivered orders for an outlet.",
        "metric.net_adjusted": "Sales minus refunds for delivered orders.",
    }


def _units() -> dict:
    return {
        "metric.delivered_order_amount": "money",
        "metric.delivered_orders": "count",
        "metric.net_adjusted": "money",
    }


def test_net_sales_blocks_delivered_amount() -> None:
    """The pilot failure: net sales must not run the delivered-amount recipe."""
    reason = contradicted_recipe(
        "How many orders did we have in December 2025, and what were net sales?",
        "metric.delivered_order_amount",
        _meanings(),
        _units(),
    )
    assert reason is not None
    assert "refund" in reason


def test_net_sales_allows_refund_adjusted_metric() -> None:
    """A metric that states the refund deduction is compatible."""
    assert (
        contradicted_recipe(
            "What were net sales in December?",
            "metric.net_adjusted",
            _meanings(),
            _units(),
        )
        is None
    )


def test_orders_count_keeps_today_behavior() -> None:
    """A count can never answer a deduction term, so counts are untouched."""
    assert (
        contradicted_recipe(
            "How many orders did we have in December 2025, and what were net sales?",
            "metric.delivered_orders",
            _meanings(),
            _units(),
        )
        is None
    )


def test_unknown_unit_blocks_nothing() -> None:
    """Without a known money unit the gate stays inert."""
    assert (
        contradicted_recipe(
            "What were net sales in December?",
            "metric.mystery",
            {},
            {},
        )
        is None
    )


def test_unknown_metric_meaning_blocks_money() -> None:
    """An unverifiable money meaning cannot justify a deduction term."""
    assert (
        contradicted_recipe(
            "What were net sales in December?",
            "metric.mystery",
            {},
            {"metric.mystery": "money"},
        )
        is not None
    )


def test_house_terms_cite_their_source() -> None:
    """Every house term names where its definition comes from."""
    assert HOUSE_TERMS["net sales"]["source"]
