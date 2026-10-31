"""Default validation: periods, metric references, ambiguous best (P09.4)."""

from charie.shared.knowledge.defaults import validate_default


def test_allowed_periods() -> None:
    for period in (
        "latest_full_month",
        "latest_full_week",
        "latest_full_quarter",
        "latest_full_year",
    ):
        assert validate_default("period", period, set()) == []
    assert validate_default("period", "last century", set()) != []
    assert validate_default("period", "", set()) != []
    assert validate_default("last_week", "last_full_week", set()) == []
    assert validate_default("last_week", "last_7_days", set()) == []
    assert validate_default("last_week", "latest_full_week", set()) != []


def test_metric_reference() -> None:
    tested = {"metric.net_sales"}
    assert validate_default("sales", "metric.net_sales", tested) == []
    assert validate_default("sales", "metric.gross", tested) != []
    assert validate_default("sales", "", tested) != []
    assert validate_default("nonsense", "metric.net_sales", tested) != []


def test_best_ambiguous() -> None:
    tested = {"metric.net_sales", "metric.order_count"}
    assert validate_default("best", "", tested) == []
    assert validate_default("best", "metric.net_sales", tested) == []
    assert validate_default("best", "metric.gross", tested) != []
