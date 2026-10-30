"""The calculator on hand-worked values: exact decimals, no floats, plain words."""

from datetime import date
from decimal import Decimal

import pytest

from charie.shared.calc.core import (
    CalcError,
    ResultTable,
    difference,
    percent_change,
    period_status,
    share,
    trend,
)


def test_total_is_exact() -> None:
    with ResultTable(["v"], [["0.1"], ["0.2"]]) as table:
        assert table.total("v") == Decimal("0.3")


def test_total_skips_empty_values() -> None:
    with ResultTable(["v"], [["0.1"], [None], [""], ["0.2"]]) as table:
        assert table.total("v") == Decimal("0.3")


def test_total_of_nothing_is_none() -> None:
    with ResultTable(["v"], [[None], [""]]) as table:
        assert table.total("v") is None


def test_difference_negative() -> None:
    assert difference(Decimal("93.80"), Decimal("100.00")) == Decimal("-6.20")


def test_percent_change() -> None:
    assert percent_change(Decimal("93.8"), 100) == Decimal("-6.2")
    assert percent_change(43800, 41200) == Decimal("6.310679611650485436893203883")


def test_percent_change_from_zero_is_none() -> None:
    assert percent_change(10, 0) is None


def test_share() -> None:
    assert share(1, 4) == Decimal("25")


def test_share_of_zero_is_none() -> None:
    assert share(1, 0) is None


def test_rank_with_ties() -> None:
    with ResultTable(["name", "v"], [["a", 5], ["b", 3], ["c", 3], ["d", 1]]) as table:
        assert [rank for rank, _ in table.rank("v")] == [1, 2, 2, 4]


def test_mixed_currencies_refused() -> None:
    with pytest.raises(
        CalcError,
        match=r"different currencies \(`USD` and `EUR`\)",
    ):
        difference(10, 5, currency_new="USD", currency_old="EUR")
    with pytest.raises(CalcError):
        percent_change(10, 5, currency_new="USD", currency_old="EUR")
    with pytest.raises(CalcError):
        share(1, 4, currency_new="USD", currency_old="EUR")


def test_float_refused() -> None:
    with pytest.raises(CalcError, match="Use Decimal or str for numbers, not float."):
        difference(0.1, 0.2)
    with pytest.raises(CalcError, match="Use Decimal or str for numbers, not float."):
        ResultTable(["v"], [[0.1]])


def test_trend_up_two_of_three_steps() -> None:
    found = trend([10, 12, 11, 15])
    assert found.direction == "up"
    assert found.steps_that_way == 2
    assert found.is_real is True


def test_trend_not_real_one_of_two_steps() -> None:
    found = trend([10, 9, 11])
    assert found.direction == "up"
    assert found.steps_that_way == 1
    assert found.is_real is False


def test_two_points_not_a_trend() -> None:
    found = trend([10, 12])
    assert found.direction == "flat"
    assert found.is_real is False


def test_flat() -> None:
    found = trend([5, 5, 5])
    assert found.direction == "flat"
    assert found.is_real is False


def test_period_complete() -> None:
    found = period_status(date(2025, 12, 1), date(2025, 12, 31), date(2025, 12, 31))
    assert found.status == "complete"
    assert found.note == ""


def test_period_partial_month_note() -> None:
    found = period_status(date(2025, 12, 1), date(2025, 12, 31), date(2025, 12, 18))
    assert found.status == "partial"
    assert found.note == "December has data up to the 18th only."


def test_period_last_day_not_loaded() -> None:
    found = period_status(
        date(2025, 12, 1), date(2025, 12, 31), date(2025, 12, 31), last_day_complete=False
    )
    assert found.status == "partial"


def test_period_no_data_note() -> None:
    found = period_status(date(2026, 1, 1), date(2026, 1, 31), date(2025, 12, 31))
    assert found.status == "no_data"
    assert found.note == (
        "There's no data for this period yet. The data only goes up to `31 Dec 2025`."
    )


def test_ordinals() -> None:
    from charie.shared.calc.core import _ordinal

    assert [_ordinal(day) for day in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 31)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
        "23rd",
        "31st",
    ]
