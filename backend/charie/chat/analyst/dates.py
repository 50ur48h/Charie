"""Period expressions and the date resolver: the AI never types dates (P10.3).

A question names a period as a small fixed form (`last_full_week`,
`month 2025-12`); code turns it into real dates using the calendar
entries, the time zone and the date the data ends, and marks periods
the data only partly covers.
"""

import calendar as pycalendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from charie.shared.calc.core import period_status
from charie.shared.text.numbers import format_date, format_period

PeriodUnit = Literal["day", "week", "month", "quarter", "year"]
PeriodKind = Literal[
    "this_unit",
    "last_full_unit",
    "units_ago",
    "last_n_units",
    "latest_full_unit",
    "month",
    "quarter",
    "year",
    "fiscal_quarter",
    "fiscal_year",
    "same_period_before",
    "same_period_last_year",
    "custom",
    "all_time",
]

_THIS_NAMES = {
    "today": "day",
    "this_week": "week",
    "this_month": "month",
    "this_quarter": "quarter",
    "this_year": "year",
}
_LAST_FULL_NAMES = {
    "yesterday": "day",
    "last_full_week": "week",
    "last_full_month": "month",
    "last_full_quarter": "quarter",
    "last_full_year": "year",
}
_SAYS_THIS = {
    "day": "today",
    "week": "this week",
    "month": "this month",
    "quarter": "this quarter",
    "year": "year to date",
}
_SAYS_LAST_FULL = {
    "day": "yesterday",
    "week": "last week",
    "month": "last month",
    "quarter": "last quarter",
    "year": "last year",
}


class PeriodError(Exception):
    """A period the resolver can't use, in the owner's words."""


class PeriodExpression(BaseModel):
    """One period in the AI's flat form (used inside AI forms).

    Each kind needs its own fields; anything else is a `PeriodError`.
    """

    kind: PeriodKind = Field(description="The kind of period, from the fixed list.")
    unit: PeriodUnit | None = Field(default=None, description="day, week, month, quarter or year.")
    count: int | None = Field(default=None, description="How many units back or how many to take.")
    number: int | None = Field(default=None, description="The month or quarter number.")
    year: int | None = Field(default=None, description="The calendar or fiscal year.")
    of_period: int | None = Field(default=None, description="Which earlier period to compare with.")
    start: date | None = Field(default=None, description="Custom range start, YYYY-MM-DD.")
    end: date | None = Field(default=None, description="Custom range end, YYYY-MM-DD.")

    @model_validator(mode="after")
    def _needs_its_fields(self) -> "PeriodExpression":
        need: dict[str, list[str]] = {
            "this_unit": ["unit"],
            "last_full_unit": ["unit"],
            "units_ago": ["unit", "count"],
            "last_n_units": ["unit", "count"],
            "latest_full_unit": ["unit"],
            "month": ["number"],
            "quarter": ["number"],
            "year": ["year"],
            "fiscal_quarter": ["number"],
            "fiscal_year": ["year"],
            "same_period_before": ["of_period"],
            "same_period_last_year": ["of_period"],
            "custom": ["start", "end"],
            "all_time": [],
        }
        for slot in need[self.kind]:
            if getattr(self, slot) is None:
                raise PeriodError(f"This kind of period needs a {slot}.")
        if (
            self.kind == "custom"
            and self.start is not None
            and self.end is not None
            and self.end < self.start
        ):
            raise PeriodError("The end date comes before the start date.")
        return self

    def says(self) -> str:
        """The period in the owner's words (never written by the AI)."""
        kind, unit = self.kind, self.unit or "month"
        if kind == "this_unit":
            return _SAYS_THIS[unit]
        if kind == "last_full_unit":
            return _SAYS_LAST_FULL[unit]
        if kind == "units_ago":
            return f"{self.count} {unit}s ago"
        if kind == "last_n_units":
            if unit == "day":
                return f"last {self.count} days"
            return f"past {self.count} {unit}s"
        if kind == "latest_full_unit":
            return f"the latest full {unit}"
        if kind in ("month", "quarter"):
            return _named_period_says(kind, self.number or 1, self.year)
        if kind == "year":
            return str(self.year)
        if kind == "fiscal_quarter":
            return f"fiscal Q{self.number}"
        if kind == "fiscal_year":
            return f"FY {self.year}"
        if kind == "same_period_before":
            return f"the {unit} before"
        if kind == "same_period_last_year":
            return f"same {unit} last year"
        if kind == "custom" and self.start is not None and self.end is not None:
            return format_period(self.start.isoformat(), self.end.isoformat())
        return "ever"

    def short_text(self) -> str:
        """The short name, exactly as `from_short_text` reads it."""
        kind = self.kind
        if kind == "this_unit":
            return next(name for name, item in _THIS_NAMES.items() if item == self.unit)
        if kind == "last_full_unit":
            return next(name for name, item in _LAST_FULL_NAMES.items() if item == self.unit)
        if kind == "units_ago":
            return f"{self.unit}s_ago {self.count}"
        if kind == "last_n_units":
            plural = self.unit + "s" if self.unit != "day" else "days"
            return f"last_{self.count}_{plural}"
        if kind == "latest_full_unit":
            return f"latest_full_{self.unit}"
        if kind == "month":
            return (
                f"month {self.year}-{self.number:02d}"
                if self.year is not None
                else f"month {self.number}"
            )
        if kind == "quarter":
            if self.year is not None:
                return f"quarter {self.year}-Q{self.number}"
            return f"quarter Q{self.number}"
        if kind == "year":
            return f"year {self.year}"
        if kind == "fiscal_quarter":
            if self.year is not None:
                return f"fiscal_quarter {self.year}-Q{self.number}"
            return f"fiscal_quarter Q{self.number}"
        if kind == "fiscal_year":
            return f"fiscal_year {self.year}"
        if kind == "same_period_before":
            return f"same_period_before p{self.of_period}"
        if kind == "same_period_last_year":
            return f"same_period_last_year p{self.of_period}"
        if kind == "custom" and self.start is not None and self.end is not None:
            return f"custom {self.start.isoformat()}..{self.end.isoformat()}"
        return "all_time"

    @classmethod
    def from_short_text(cls, text: str) -> "PeriodExpression":
        """Read any short name from the plan's table, or fail plainly."""
        import re

        words = text.strip().lower()
        if words in _THIS_NAMES:
            return cls(kind="this_unit", unit=_THIS_NAMES[words])
        if words in _LAST_FULL_NAMES:
            return cls(kind="last_full_unit", unit=_LAST_FULL_NAMES[words])
        match = re.fullmatch(r"(day|week|month|quarter|year)s_ago (\d+)", words)
        if match:
            return cls(kind="units_ago", unit=match.group(1), count=int(match.group(2)))
        match = re.fullmatch(r"last_(\d+)_(days|weeks|months|quarters|years)", words)
        if match:
            unit = match.group(2)[:-1]
            return cls(kind="last_n_units", unit=unit, count=int(match.group(1)))
        match = re.fullmatch(r"latest_full_(day|week|month|quarter|year)", words)
        if match:
            return cls(kind="latest_full_unit", unit=match.group(1))
        match = re.fullmatch(r"month (\d{4})-(\d{1,2})", words)
        if match:
            return cls(kind="month", number=int(match.group(2)), year=int(match.group(1)))
        match = re.fullmatch(r"month (\d{1,2})", words)
        if match:
            return cls(kind="month", number=int(match.group(1)))
        match = re.fullmatch(r"quarter (\d{4})-q(\d)", words)
        if match:
            return cls(kind="quarter", number=int(match.group(2)), year=int(match.group(1)))
        match = re.fullmatch(r"quarter q?(\d)", words)
        if match:
            return cls(kind="quarter", number=int(match.group(1)))
        match = re.fullmatch(r"year (\d{4})", words)
        if match:
            return cls(kind="year", year=int(match.group(1)))
        match = re.fullmatch(r"fiscal_quarter (\d{4})-q(\d)", words)
        if match:
            return cls(kind="fiscal_quarter", number=int(match.group(2)), year=int(match.group(1)))
        match = re.fullmatch(r"fiscal_quarter q?(\d)", words)
        if match:
            return cls(kind="fiscal_quarter", number=int(match.group(1)))
        match = re.fullmatch(r"fiscal_year (\d{4})", words)
        if match:
            return cls(kind="fiscal_year", year=int(match.group(1)))
        match = re.fullmatch(r"same_period_before p(\d+)", words)
        if match:
            return cls(kind="same_period_before", of_period=int(match.group(1)))
        match = re.fullmatch(r"same_period_last_year p(\d+)", words)
        if match:
            return cls(kind="same_period_last_year", of_period=int(match.group(1)))
        match = re.fullmatch(r"custom (\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", words)
        if match:
            return cls(
                kind="custom",
                start=date.fromisoformat(match.group(1)),
                end=date.fromisoformat(match.group(2)),
            )
        if words == "all_time":
            return cls(kind="all_time")
        raise PeriodError(f'I don\'t know the period name "{text.strip()}".')


_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _named_period_says(kind: str, number: int, year: int | None) -> str:
    """`month 2025-12` says "December 2025"; without a year, "in March"."""
    if kind == "month":
        name = _MONTHS[number - 1]
        return f"{name} {year}" if year is not None else f"in {name}"
    if year is not None:
        return f"Q{number} {year}"
    return f"Q{number}"


@dataclass
class DateContext:
    """What the resolver needs: the anchor inputs and the calendar."""

    today: date
    data_through: date | None
    data_from: date | None
    week_start: str = "monday"
    fiscal_start_month: int = 1
    time_zone: str = "UTC"


@dataclass
class ResolvedPeriod:
    """One expression turned into real dates."""

    label: str
    expression: PeriodExpression
    start: date
    end: date
    full_end: date
    partial: bool
    no_data: bool
    text: str
    note: str


@dataclass
class PeriodSet:
    """Every period of one question, plus the anchor note."""

    periods: list[ResolvedPeriod] = field(default_factory=list)
    anchor_note: str = ""


def _month_end(year: int, month: int) -> date:
    """The last day of a month."""
    return date(year, month, pycalendar.monthrange(year, month)[1])


def _shift_month(year: int, month: int, steps: int) -> tuple[int, int]:
    """Move months, wrapping the year."""
    total = (year * 12 + (month - 1)) + steps
    return total // 12, total % 12 + 1


def _week_start(day: date, week_start: str) -> date:
    """The week's first day (Monday, or Sunday when the calendar says so)."""
    if week_start == "sunday":
        return day - timedelta(days=(day.weekday() + 1) % 7)
    return day - timedelta(days=day.weekday())


def _unit_start(day: date, unit: str, week_start: str, fiscal_start: int) -> date:
    """The first day of the unit holding `day`."""
    if unit == "day":
        return day
    if unit == "week":
        return _week_start(day, week_start)
    if unit == "month":
        return date(day.year, day.month, 1)
    if unit == "quarter":
        return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    if unit == "year":
        return date(day.year, 1, 1)
    back = (day.month - fiscal_start) % 12
    start_year, start_month = _shift_month(day.year, day.month, -back)
    return date(start_year, start_month, 1)


def _unit_end(day: date, unit: str, week_start: str, fiscal_start: int) -> date:
    """The last day of the unit holding `day`."""
    if unit == "day":
        return day
    if unit == "week":
        return _week_start(day, week_start) + timedelta(days=6)
    if unit == "month":
        return _month_end(day.year, day.month)
    if unit == "quarter":
        year, month = _shift_month(day.year, 3 * ((day.month - 1) // 3) + 1, 3)
        return date(year, month, 1) - timedelta(days=1)
    first = _unit_start(day, unit, week_start, fiscal_start)
    year, month = _shift_month(first.year, first.month, 12)
    return date(year, month, 1) - timedelta(days=1)


def _quarter_start(year: int, number: int) -> date:
    """The first day of calendar quarter `number`."""
    return date(year, 3 * (number - 1) + 1, 1)


def _whole_unit(start: date, end: date, week_start: str) -> str | None:
    """The calendar unit the range fills exactly, if any."""
    for unit in ("day", "week", "month", "quarter", "year"):
        if start == _unit_start(start, unit, week_start, 1) and end == _unit_end(
            start, unit, week_start, 1
        ):
            return unit
    return None


def _back_a_year(day: date) -> date:
    """The same date a year earlier (29 Feb becomes 28 Feb)."""
    try:
        return date(day.year - 1, day.month, day.day)
    except ValueError:
        return date(day.year - 1, 2, 28)


def _previous_units(anchor: date, unit: str, count: int, week_start: str) -> tuple[date, date]:
    """The `count` most recent whole units, ending at or before the anchor."""
    top = anchor
    if top != _unit_end(top, unit, week_start, 1):
        top = _unit_start(top, unit, week_start, 1) - timedelta(days=1)
    end = _unit_end(top, unit, week_start, 1)
    day = top
    for _ in range(count - 1):
        day = _unit_start(day, unit, week_start, 1) - timedelta(days=1)
    return _unit_start(day, unit, week_start, 1), end


def _most_recent_start(anchor: date, start_of_year: date) -> int:
    """The latest year whose period start has started by the anchor."""
    return anchor.year if start_of_year <= anchor else anchor.year - 1


def _raw_range(
    expression: PeriodExpression,
    anchor: date,
    week_start: str,
    fiscal_start: int,
    resolved: list[ResolvedPeriod],
) -> tuple[date, date]:
    """The expression's full dates, before the data window cuts them."""
    kind = expression.kind
    if kind == "this_unit":
        unit = expression.unit or "day"
        return _unit_start(anchor, unit, week_start, fiscal_start), _unit_end(
            anchor, unit, week_start, fiscal_start
        )
    if kind == "last_full_unit":
        unit = expression.unit or "day"
        before = _unit_start(anchor, unit, week_start, fiscal_start) - timedelta(days=1)
        return _unit_start(before, unit, week_start, fiscal_start), _unit_end(
            before, unit, week_start, fiscal_start
        )
    if kind == "units_ago":
        unit, count = expression.unit or "day", expression.count or 1
        day = anchor
        for _ in range(count):
            day = _unit_start(day, unit, week_start, fiscal_start) - timedelta(days=1)
        return _unit_start(day, unit, week_start, fiscal_start), _unit_end(
            day, unit, week_start, fiscal_start
        )
    if kind == "last_n_units":
        unit, count = expression.unit or "day", expression.count or 1
        if unit == "day":
            return anchor - timedelta(days=count - 1), anchor
        return _previous_units(anchor, unit, count, week_start)
    if kind == "latest_full_unit":
        unit = expression.unit or "month"
        if anchor == _unit_end(anchor, unit, week_start, fiscal_start):
            return _unit_start(anchor, unit, week_start, fiscal_start), anchor
        before = _unit_start(anchor, unit, week_start, fiscal_start) - timedelta(days=1)
        return _unit_start(before, unit, week_start, fiscal_start), _unit_end(
            before, unit, week_start, fiscal_start
        )
    if kind == "month":
        number = expression.number or 1
        year = expression.year
        if year is None:
            year = _most_recent_start(anchor, date(anchor.year, number, 1))
        return date(year, number, 1), _month_end(year, number)
    if kind == "quarter":
        number = expression.number or 1
        year = expression.year
        if year is None:
            year = _most_recent_start(anchor, _quarter_start(anchor.year, number))
        first = _quarter_start(year, number)
        last_year, last_month = _shift_month(year, 3 * (number - 1) + 1, 3)
        return first, date(last_year, last_month, 1) - timedelta(days=1)
    if kind == "year":
        return date(expression.year or anchor.year, 1, 1), date(
            expression.year or anchor.year, 12, 31
        )
    if kind == "fiscal_quarter":
        number = expression.number or 1
        if expression.year is not None:
            first_year, first_month = _shift_month(expression.year, fiscal_start, 3 * (number - 1))
        else:
            started = _most_recent_start(anchor, date(anchor.year, fiscal_start, 1))
            first_year, first_month = _shift_month(started, fiscal_start, 3 * (number - 1))
        first = date(first_year, first_month, 1)
        last_year, last_month = _shift_month(first_year, first_month, 3)
        return first, date(last_year, last_month, 1) - timedelta(days=1)
    if kind == "fiscal_year":
        year = expression.year or anchor.year
        first = date(year, fiscal_start, 1)
        last_year, last_month = _shift_month(year, fiscal_start, 12)
        return first, date(last_year, last_month, 1) - timedelta(days=1)
    if kind in ("same_period_before", "same_period_last_year"):
        index = (expression.of_period or 0) - 1
        if index < 0 or index >= len(resolved):
            raise PeriodError("A comparison period must point to an earlier period.")
        ref = resolved[index]
        if kind == "same_period_last_year":
            if _whole_unit(ref.start, ref.end, week_start) == "week":
                shift = timedelta(days=364)
                return ref.start - shift, ref.end - shift
            return _back_a_year(ref.start), _back_a_year(ref.end)
        whole = _whole_unit(ref.start, ref.end, week_start)
        if whole is not None:
            before = _unit_start(ref.start, whole, week_start, fiscal_start) - timedelta(days=1)
            return _unit_start(before, whole, week_start, fiscal_start), _unit_end(
                before, whole, week_start, fiscal_start
            )
        if ref.start.day == 1 and ref.start.month == ref.end.month:
            year, month = _shift_month(ref.start.year, ref.start.month, -1)
            last = pycalendar.monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, min(ref.end.day, last))
        length = (ref.end - ref.start).days
        return ref.start - timedelta(days=length + 1), ref.start - timedelta(days=1)
    if kind == "custom":
        assert expression.start is not None and expression.end is not None
        return expression.start, expression.end
    raise PeriodError(f"I don't know the period kind {kind}.")


def _resolve_one(
    expression: PeriodExpression,
    label: str,
    anchor: date,
    through: date | None,
    date_from: date | None,
    week_start: str,
    fiscal_start: int,
    resolved: list[ResolvedPeriod],
) -> ResolvedPeriod:
    """Cut one raw range at the data window and mark what the data covers."""
    raw_start, full_end = _raw_range(expression, anchor, week_start, fiscal_start, resolved)
    start = raw_start
    if through is not None and start > through:
        status = period_status(start, full_end, through)
        return ResolvedPeriod(
            label=label,
            expression=expression,
            start=start,
            end=full_end,
            full_end=full_end,
            partial=status.status == "partial",
            no_data=status.status == "no_data",
            text=format_period(start.isoformat(), full_end.isoformat()),
            note=status.note,
        )
    end = min(full_end, through) if through is not None else full_end
    if date_from is not None and end < date_from:
        text = format_period(raw_start.isoformat(), full_end.isoformat())
        return ResolvedPeriod(
            label=label,
            expression=expression,
            start=raw_start,
            end=full_end,
            full_end=full_end,
            partial=False,
            no_data=True,
            text=text,
            note=(
                f"There's no data for {text}. "
                f"The data starts on {format_date(date_from.isoformat())}."
            ),
        )
    forced_partial = False
    if date_from is not None and start < date_from <= end:
        start = date_from
        forced_partial = True
    # The status reads the full range against the data's end, so a whole
    # month cut by the data still says so ("December has data up to...").
    if through is None:
        status = period_status(start, end, end)
    else:
        status = period_status(start, full_end, through)
    partial = forced_partial or status.status == "partial"
    if forced_partial:
        text = format_period(start.isoformat(), end.isoformat())
        note = (
            f"{text} is only partly covered: "
            f"the data starts on {format_date(date_from.isoformat())}."
        )
    else:
        text = format_period(start.isoformat(), end.isoformat())
        note = status.note
    return ResolvedPeriod(
        label=label,
        expression=expression,
        start=start,
        end=end,
        full_end=full_end,
        partial=partial,
        no_data=status.status == "no_data",
        text=text,
        note=note,
    )


def _anchor_note(today: date, anchor: date) -> str:
    """Why the data's end stands in for today."""
    if anchor >= today:
        return ""
    day = format_date(anchor.isoformat())
    return f"The data only goes up to {day}, so I'm treating {day} as today."


def resolve_periods(expressions: list[PeriodExpression], ctx: DateContext) -> PeriodSet:
    """Turn one question's period expressions into real dates.

    The anchor is the earlier of today and the data's end. Ranges are cut
    at the data window; `all_time` with no data behind it answers today.
    """
    anchor = ctx.today
    if ctx.data_through is not None and ctx.data_through < anchor:
        anchor = ctx.data_through
    through = ctx.data_through
    resolved: list[ResolvedPeriod] = []
    for position, expression in enumerate(expressions, start=1):
        if expression.kind == "all_time":
            start = ctx.data_from or through or anchor
            end = through or anchor
            text = format_period(start.isoformat(), end.isoformat())
            if through is None:
                status = period_status(start, end, end)
            else:
                status = period_status(start, end, through)
            resolved.append(
                ResolvedPeriod(
                    label=f"p{position}",
                    expression=expression,
                    start=start,
                    end=end,
                    full_end=end,
                    partial=status.status == "partial",
                    no_data=status.status == "no_data",
                    text=text,
                    note=status.note,
                )
            )
            continue
        resolved.append(
            _resolve_one(
                expression,
                f"p{position}",
                anchor,
                through,
                ctx.data_from,
                ctx.week_start,
                ctx.fiscal_start_month,
                resolved,
            )
        )
    return PeriodSet(periods=resolved, anchor_note=_anchor_note(ctx.today, anchor))
