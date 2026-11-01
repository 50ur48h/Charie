"""Period expressions and the resolver: every named period (P10.3)."""

from datetime import date

import pytest

from charie.chat.analyst.dates import (
    DateContext,
    PeriodError,
    PeriodExpression,
    resolve_periods,
)
from charie.shared.text.numbers import format_date

TODAY = date(2026, 10, 27)
THROUGH = date(2025, 12, 31)
FROM = date(2024, 1, 1)


def _anchor(through) -> str:
    day = format_date(through.isoformat())
    return f"The data only goes up to {day}, so I'm treating {day} as today."


DASH = "–"


def _ctx(
    through: date | None = THROUGH,
    week_start: str = "monday",
    fiscal: int = 1,
    date_from: date | None = FROM,
) -> DateContext:
    return DateContext(
        today=TODAY,
        data_through=through,
        data_from=date_from,
        week_start=week_start,
        fiscal_start_month=fiscal,
        time_zone="UTC",
    )


def _expression(short: str) -> PeriodExpression:
    return PeriodExpression.from_short_text(short)


def D(day: int, month: int, year: int) -> date:
    return date(year, month, day)


CASES = [
    (
        "this_month_data_ends_31_dec",
        ["this_month"],
        {},
        D(1, 12, 2025),
        D(31, 12, 2025),
        f"1{DASH}31 Dec 2025",
        False,
        False,
        "",
    ),
    ("today", ["today"], {}, D(31, 12, 2025), D(31, 12, 2025), "31 Dec 2025", False, False, ""),
    (
        "yesterday",
        ["yesterday"],
        {},
        D(30, 12, 2025),
        D(30, 12, 2025),
        "30 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "last_week",
        ["last_full_week"],
        {},
        D(22, 12, 2025),
        D(28, 12, 2025),
        f"22{DASH}28 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "this_week_partial",
        ["this_week"],
        {},
        D(29, 12, 2025),
        D(31, 12, 2025),
        f"29{DASH}31 Dec 2025",
        True,
        False,
        "This period has data up to `31 Dec 2025` only.",
    ),
    (
        "three_weeks_ago",
        ["weeks_ago 3"],
        {},
        D(8, 12, 2025),
        D(14, 12, 2025),
        f"8{DASH}14 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "last_month",
        ["last_full_month"],
        {},
        D(1, 11, 2025),
        D(30, 11, 2025),
        f"1{DASH}30 Nov 2025",
        False,
        False,
        "",
    ),
    (
        "two_months_ago",
        ["months_ago 2"],
        {},
        D(1, 10, 2025),
        D(31, 10, 2025),
        f"1{DASH}31 Oct 2025",
        False,
        False,
        "",
    ),
    (
        "q4_no_year",
        ["quarter 2025-Q4"],
        {},
        D(1, 10, 2025),
        D(31, 12, 2025),
        f"1 Oct {DASH} 31 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "march_no_year",
        ["month 3"],
        {},
        D(1, 3, 2025),
        D(31, 3, 2025),
        f"1{DASH}31 Mar 2025",
        False,
        False,
        "",
    ),
    (
        "same_month_last_year",
        ["month 2025-12", "same_period_last_year p1"],
        {"index": 1},
        D(1, 12, 2024),
        D(31, 12, 2024),
        f"1{DASH}31 Dec 2024",
        False,
        False,
        "",
    ),
    (
        "month_before",
        ["month 2025-12", "same_period_before p1"],
        {"index": 1},
        D(1, 11, 2025),
        D(30, 11, 2025),
        f"1{DASH}30 Nov 2025",
        False,
        False,
        "",
    ),
    (
        "partial_month",
        ["this_month"],
        {"through": date(2025, 12, 18)},
        D(1, 12, 2025),
        D(18, 12, 2025),
        f"1{DASH}18 Dec 2025",
        True,
        False,
        "December has data up to the 18th only.",
    ),
    (
        "partial_month_before",
        ["this_month", "same_period_before p1"],
        {"through": date(2025, 12, 18), "index": 1},
        D(1, 11, 2025),
        D(18, 11, 2025),
        f"1{DASH}18 Nov 2025",
        False,
        False,
        "",
    ),
    (
        "last_7_days",
        ["last_7_days"],
        {},
        D(25, 12, 2025),
        D(31, 12, 2025),
        f"25{DASH}31 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "last_3_months",
        ["last_3_months"],
        {},
        D(1, 10, 2025),
        D(31, 12, 2025),
        f"1 Oct {DASH} 31 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "last_3_months_partial",
        ["last_3_months"],
        {"through": date(2025, 12, 18)},
        D(1, 9, 2025),
        D(30, 11, 2025),
        f"1 Sep {DASH} 30 Nov 2025",
        False,
        False,
        "",
    ),
    (
        "year_to_date",
        ["this_year"],
        {"through": date(2025, 12, 18)},
        D(1, 1, 2025),
        D(18, 12, 2025),
        f"1 Jan {DASH} 18 Dec 2025",
        True,
        False,
        "This period has data up to `18 Dec 2025` only.",
    ),
    (
        "last_year",
        ["last_full_year"],
        {},
        D(1, 1, 2024),
        D(31, 12, 2024),
        f"1 Jan {DASH} 31 Dec 2024",
        False,
        False,
        "",
    ),
    (
        "latest_full_month",
        ["latest_full_month"],
        {"through": date(2025, 12, 18)},
        D(1, 11, 2025),
        D(30, 11, 2025),
        f"1{DASH}30 Nov 2025",
        False,
        False,
        "",
    ),
    (
        "same_week_last_year",
        ["last_full_week", "same_period_last_year p1"],
        {"index": 1},
        D(23, 12, 2024),
        D(29, 12, 2024),
        f"23{DASH}29 Dec 2024",
        False,
        False,
        "",
    ),
    (
        "future_month",
        ["month 2026-03"],
        {},
        D(1, 3, 2026),
        D(31, 3, 2026),
        f"1{DASH}31 Mar 2026",
        False,
        True,
        "There's no data for this period yet. The data only goes up to `31 Dec 2025`.",
    ),
    (
        "before_data",
        ["month 2023-12"],
        {},
        D(1, 12, 2023),
        D(31, 12, 2023),
        f"1{DASH}31 Dec 2023",
        False,
        True,
        "There's no data for 1\u201331 Dec 2023. The data starts on 1 Jan 2024.",
    ),
    (
        "custom_range",
        ["custom 2025-03-01..2025-05-31"],
        {},
        D(1, 3, 2025),
        D(31, 5, 2025),
        f"1 Mar {DASH} 31 May 2025",
        False,
        False,
        "",
    ),
    (
        "all_time",
        ["all_time"],
        {},
        D(1, 1, 2024),
        D(31, 12, 2025),
        f"1 Jan 2024 {DASH} 31 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "weeks_start_sunday",
        ["last_full_week"],
        {"week_start": "sunday"},
        D(21, 12, 2025),
        D(27, 12, 2025),
        f"21{DASH}27 Dec 2025",
        False,
        False,
        "",
    ),
    (
        "fiscal_year_april",
        ["fiscal_year 2025"],
        {"fiscal": 4},
        D(1, 4, 2025),
        D(31, 12, 2025),
        f"1 Apr {DASH} 31 Dec 2025",
        True,
        False,
        "This period has data up to `31 Dec 2025` only.",
    ),
]


@pytest.mark.parametrize(
    "case_id,shorts,options,start,end,text,partial,no_data,note",
    CASES,
    ids=[row[0] for row in CASES],
)
def test_resolve_period(case_id, shorts, options, start, end, text, partial, no_data, note) -> None:
    del case_id
    ctx = _ctx(
        through=options.get("through", THROUGH),
        week_start=options.get("week_start", "monday"),
        fiscal=options.get("fiscal", 1),
    )
    resolved = resolve_periods([_expression(item) for item in shorts], ctx)
    period = resolved.periods[options.get("index", 0)]
    assert (period.start, period.end) == (start, end)
    assert period.text == text
    assert period.partial is partial
    assert period.no_data is no_data
    assert period.note == note
    assert resolved.anchor_note == _anchor(options.get("through", THROUGH))


def test_expression_kind_needs_its_fields() -> None:
    for kwargs, field in [
        ({"kind": "this_unit"}, "unit"),
        ({"kind": "units_ago", "unit": "week"}, "count"),
        ({"kind": "last_n_units", "unit": "month"}, "count"),
        ({"kind": "month"}, "number"),
        ({"kind": "year"}, "year"),
        ({"kind": "same_period_before"}, "of_period"),
        ({"kind": "custom", "start": date(2025, 1, 1)}, "end"),
    ]:
        with pytest.raises(PeriodError, match=f"needs a {field}"):
            PeriodExpression(**kwargs)


SHORT_NAMES = [
    "today",
    "this_week",
    "this_month",
    "this_quarter",
    "this_year",
    "yesterday",
    "last_full_week",
    "last_full_month",
    "last_full_quarter",
    "last_full_year",
    "weeks_ago 3",
    "last_7_days",
    "last_3_months",
    "latest_full_month",
    "month 2025-12",
    "month 3",
    "quarter 2025-Q4",
    "quarter Q4",
    "year 2025",
    "fiscal_quarter 2025-Q2",
    "fiscal_year 2025",
    "same_period_before p1",
    "same_period_last_year p1",
    "custom 2025-03-01..2025-05-31",
    "all_time",
]


@pytest.mark.parametrize("short", SHORT_NAMES)
def test_expression_short_text_round_trip(short: str) -> None:
    assert PeriodExpression.from_short_text(short).short_text() == short


def test_unknown_short_name_fails() -> None:
    with pytest.raises(PeriodError, match="don't know the period name"):
        PeriodExpression.from_short_text("last fortnight")


def test_custom_end_before_start_fails() -> None:
    with pytest.raises(PeriodError, match="comes before the start date"):
        PeriodExpression.from_short_text("custom 2025-05-31..2025-03-01")


def test_comparison_must_point_backwards() -> None:
    ctx = _ctx()
    with pytest.raises(PeriodError, match="must point to an earlier period"):
        resolve_periods(
            [
                PeriodExpression(kind="month", number=12),
                PeriodExpression(kind="same_period_before", of_period=2),
            ],
            ctx,
        )
    with pytest.raises(PeriodError, match="must point to an earlier period"):
        resolve_periods([PeriodExpression(kind="same_period_before", of_period=0)], ctx)


def test_partial_periods_carry_full_end() -> None:
    """Partial periods keep the full period end for month/week alignment."""
    cases = [
        (["this_week"], {}, D(4, 1, 2026)),
        (["this_month"], {"through": date(2025, 12, 18)}, D(31, 12, 2025)),
        (["this_year"], {"through": date(2025, 12, 18)}, D(31, 12, 2025)),
        (["fiscal_year 2025"], {"fiscal": 4}, D(31, 3, 2026)),
    ]
    for shorts, options, full_end in cases:
        ctx = _ctx(
            through=options.get("through", THROUGH),
            fiscal=options.get("fiscal", 1),
        )
        resolved = resolve_periods([_expression(item) for item in shorts], ctx)
        assert resolved.periods[0].full_end == full_end
