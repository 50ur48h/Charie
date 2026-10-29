"""Every shared example formats the same in Python and on the screens."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from charie.shared.text import numbers

EXAMPLES = json.loads(
    (
        Path(__file__).resolve().parents[4] / "frontend" / "shared" / "src" / "format-examples.json"
    ).read_text(encoding="utf-8")
)["examples"]


def _format(example):
    kind = example["kind"]
    if kind == "money":
        return numbers.format_money(
            example["value"], example.get("currency", "USD"), example.get("style", "short")
        )
    if kind == "count":
        return numbers.format_count(example["value"], example.get("style", "short"))
    if kind == "percent":
        return numbers.format_percent(example["value"])
    if kind == "change":
        return numbers.format_change(
            example["value"],
            example["unit"],
            example.get("currency", "USD"),
            example.get("style", "short"),
        )
    if kind == "ratio":
        return numbers.format_ratio(example["value"])
    if kind == "date":
        return numbers.format_date(example["value"])
    if kind == "period":
        return numbers.format_period(example["start"], example["end"])
    raise AssertionError(f"unknown kind {kind}")


@pytest.mark.parametrize("example", EXAMPLES, ids=[item.get("expect", "?") for item in EXAMPLES])
def test_shared_example(example):
    assert _format(example) == example["expect"]


def test_float_is_refused():
    with pytest.raises(TypeError, match="Use Decimal or str for numbers, not float."):
        numbers.format_money(1.5)


def test_unknown_currency_uses_code():
    assert numbers.format_money("1415000", "CHF") == "CHF 1.42M"


def test_decimal_and_int_match_strings():
    assert numbers.format_money(Decimal("1415000")) == "$1.42M"
    assert numbers.format_count(400000, "full") == "400,000"
