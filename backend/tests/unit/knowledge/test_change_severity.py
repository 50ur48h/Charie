"""Change severity: what waits for review and what doesn't (P09.9)."""

from charie.shared.knowledge.versions import is_big_change


def _entry(confidence="checked", **overrides):
    entry = {
        "key": "metric.net_sales",
        "kind": "metric",
        "title": "Net sales",
        "meaning": "Net sales",
        "details": {"kind": "simple", "table": "shop.orders"},
        "confidence": confidence,
        "sources": [],
    }
    entry.update(overrides)
    return entry


def test_recipe_dependency_big() -> None:
    """New and changed recipes alter numbers, but retests alone don't."""
    assert is_big_change("metric", "added", None, _entry()) is True
    changed = _entry(details={"kind": "simple", "table": "shop.orders", "expression": "x"})
    assert is_big_change("metric", "changed", _entry(), changed) is True
    retest = _entry(
        details={"kind": "simple", "table": "shop.orders"},
        tests=[{"name": "runs", "passed": True, "text": "ok"}],
    )
    assert is_big_change("metric", "changed", _entry(), retest) is False
    failed = _entry(tests=[{"name": "runs", "passed": False, "text": "no"}])
    assert is_big_change("metric", "changed", _entry(), failed) is True


def test_new_name_small() -> None:
    """New names, tables and columns are fresh evidence, not number changes."""
    assert is_big_change("name", "added", None, _entry(kind="name")) is False
    assert is_big_change("table", "added", None, _entry(kind="table")) is False
    assert is_big_change("default", "added", None, _entry(kind="default")) is False
    assert is_big_change("definition", "added", None, _entry(kind="definition")) is False


def test_conflict_big() -> None:
    """Conflicts and removals always wait for the owner."""
    assert is_big_change("metric", "changed", _entry(), _entry(confidence="conflicting")) is True
    assert is_big_change("metric", "removed", _entry(), None) is True
    assert is_big_change("rule", "added", None, _entry(kind="rule")) is True
    assert is_big_change("rule", "changed", _entry(kind="rule"), _entry(kind="rule")) is True


def test_owner_confirmation_small() -> None:
    """Confirming is the review, so it never blocks publishing."""
    assert (
        is_big_change(
            "default", "changed", _entry(confidence="guessed"), _entry(confidence="confirmed")
        )
        is False
    )
    assert (
        is_big_change(
            "metric", "changed", _entry(confidence="guessed"), _entry(confidence="confirmed")
        )
        is False
    )
