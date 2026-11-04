"""Whether a result can be drawn, and the sentence for when it cannot (WP11.1)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

__all__ = [
    "MARKS",
    "MAX_CATEGORIES",
    "MAX_POINTS",
    "Chart",
    "ChartRequest",
    "Frame",
    "axis_title",
    "decide",
    "kind_of",
]

#: The marks a reader can interpret without a legend explaining the mark itself.
MARKS: tuple[str, ...] = ("bar", "line", "point", "area")

#: How many categories a bar chart can show before it stops being readable.
MAX_CATEGORIES = 50

#: How many coloured series a chart may carry, which is a different and much smaller number (B-109).
MAX_SERIES = 8

#: How many points may travel inline in a spec.
MAX_POINTS = 1_000

#: What a temporal axis will accept when the catalog has not already typed the column as a date.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([T ]\d{2}:\d{2}(:\d{2})?)?")


@dataclass(frozen=True, slots=True)
class Frame:
    """A masked result, as the chart tool sees it."""

    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    #: Whether the store holds more than these rows.
    truncated: bool = False
    #: What the writer recorded each column as holding (B-103).
    column_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChartRequest:
    """The chart somebody asked for, in the terms a reader would use."""

    mark: str
    x: str
    y: str
    series: str | None = None
    title: str | None = None


@dataclass(frozen=True, slots=True)
class Chart:
    """Either a spec to render or a reason there is none. Never both, never neither."""

    spec: dict[str, object] | None = None
    declined: str | None = None
    #: Why, in a word, for the trace and for a test that wants to be specific about which rule...
    code: str | None = None

    def __post_init__(self) -> None:
        if (self.spec is None) == (self.declined is None):
            raise ValueError("a chart is a spec or a refusal, and exactly one of them")


def _decline(code: str, sentence: str) -> Chart:
    return Chart(declined=sentence, code=code)


def _is_number(value: object) -> bool:
    """Decimal counts (B-103)."""
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _is_temporal(value: object) -> bool:
    if isinstance(value, date | datetime):
        return True
    return isinstance(value, str) and bool(_ISO_DATE.match(value))


#: The same shape `_ISO_DATE` admits, taken apart so the grain can be read off it.
_ISO_PARTS = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})(?:-(?P<day>\d{2}))?"
    r"(?:[T ](?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?"
)


@dataclass(frozen=True, slots=True)
class _Instant:
    """A temporal value reduced to the fields that decide its grain."""

    month: int
    day: int | None
    #: Whether anything below a day is set to something other than midnight.
    within_day: bool


def _instant(value: object) -> _Instant | None:
    """One temporal value taken apart, or None if it is not one."""
    if isinstance(value, datetime):
        return _Instant(
            month=value.month,
            day=value.day,
            within_day=bool(value.hour or value.minute or value.second or value.microsecond),
        )
    if isinstance(value, date):
        return _Instant(month=value.month, day=value.day, within_day=False)
    if not isinstance(value, str):
        return None
    found = _ISO_PARTS.match(value)
    if found is None:
        return None
    clock = (found.group("hour"), found.group("minute"), found.group("second"))
    day = found.group("day")
    return _Instant(
        month=int(found.group("month")),
        day=int(day) if day is not None else None,
        within_day=any(part is not None and int(part) != 0 for part in clock),
    )


def _time_grain(values: Sequence[object]) -> str | None:
    """The coarsest Vega-Lite `timeUnit` every value sits exactly on, or None."""
    instants = [_instant(value) for value in _present(values)]
    if not instants or any(instant is None for instant in instants):
        return None
    known = [instant for instant in instants if instant is not None]
    if any(instant.within_day for instant in known):
        # Something below a day is set, so a day is not the unit.
        return None
    if any(instant.day not in (None, 1) for instant in known):
        return "yearmonthdate"
    if all(instant.month == 1 for instant in known):
        return "year"
    return "yearmonth"


def _stale_numeric(frame: Frame, name: str) -> bool:
    """Whether this column is unjudgeable rather than non-numeric (B-103)."""
    if frame.column_types:
        return False
    values = _present(_column_values(frame, name))
    if not values:
        return False
    return all(isinstance(value, str) and _parses_as_number(value) for value in values)


def _parses_as_number(value: str) -> bool:
    try:
        Decimal(value)
    except InvalidOperation:
        return False
    return True


def _column_values(frame: Frame, name: str) -> tuple[object, ...]:
    index = frame.columns.index(name)
    return tuple(row[index] for row in frame.rows if index < len(row))


def _present(values: Sequence[object]) -> tuple[object, ...]:
    return tuple(value for value in values if value is not None)


def kind_of(values: Sequence[object]) -> Literal["quantitative", "temporal", "nominal"]:
    """What a column is, judged from the values rather than from its name."""
    present = _present(values)
    if not present:
        return "nominal"
    if all(_is_number(value) for value in present):
        return "quantitative"
    if all(_is_temporal(value) for value in present):
        return "temporal"
    return "nominal"


def decide(frame: Frame, request: ChartRequest) -> Chart:
    """A spec this platform will render, or the sentence saying why not."""
    if request.mark not in MARKS:
        return _decline(
            "unknown_mark",
            f"No chart was drawn: {request.mark!r} is not a chart type this product renders. "
            f"It draws {', '.join(MARKS)}.",
        )

    named = [name for name in (request.x, request.y, request.series) if name]
    missing = [name for name in named if name not in frame.columns]
    if missing:
        return _decline(
            "no_such_column",
            f"No chart was drawn: the result has no column called {missing[0]!r}. "
            f"It has {', '.join(frame.columns)}.",
        )

    if not frame.rows:
        return _decline("no_rows", "No chart was drawn: the query returned no rows to plot.")

    if frame.truncated or len(frame.rows) > MAX_POINTS:
        return _decline(
            "too_many_points",
            f"No chart was drawn: the result has {len(frame.rows):,} rows or more, and a chart "
            f"here shows at most {MAX_POINTS:,}. The table has all of them.",
        )

    y_values = _column_values(frame, request.y)
    if kind_of(y_values) != "quantitative":
        if _stale_numeric(frame, request.y):
            # B-103, and B-087's rule applied to a storage format.
            return _decline(
                "types_not_recorded",
                "No chart was drawn: this result was stored before the platform "
                "recorded what each column holds, so a number cannot be told "
                "from text that looks like one. Ask the question again and the "
                "new result will chart.",
            )
        return _decline(
            "y_not_numeric",
            f"No chart was drawn: {request.y!r} does not hold numbers, so there is nothing "
            "to measure up the vertical axis.",
        )

    x_values = _column_values(frame, request.x)
    x_kind = kind_of(x_values)

    if x_kind == "nominal":
        distinct = len({str(value) for value in x_values})
        if distinct > MAX_CATEGORIES:
            return _decline(
                "too_many_categories",
                f"No chart was drawn: {request.x!r} has {distinct:,} distinct values and a chart "
                f"here shows at most {MAX_CATEGORIES}. The table has all of them.",
            )
        if request.mark in ("line", "area"):
            # A line joins points in order, and nominal values have none.
            return _decline(
                "unordered_line",
                f"No chart was drawn: a {request.mark} chart joins points in order, and "
                f"{request.x!r} holds labels rather than dates or numbers. A bar chart shows "
                "these without implying a sequence.",
            )

    if request.series is not None:
        # Colour is a claim, not decoration.
        if request.series in (request.x, request.y):
            axis = "horizontal" if request.series == request.x else "vertical"
            return _decline(
                "colour_would_repeat_an_axis",
                f"No chart was drawn: {request.series!r} is already on the {axis} axis, so "
                "colouring by it would say the same thing twice. Colour is kept for a split "
                "the axes do not show — the same figures broken down by another column.",
            )
        series_distinct = len({str(value) for value in _column_values(frame, request.series)})
        if series_distinct > MAX_SERIES:
            return _decline(
                "too_many_series",
                f"No chart was drawn: {request.series!r} has {series_distinct:,} distinct values, "
                f"and a chart here colours at most {MAX_SERIES} at once — past that a ninth "
                "would repeat a colour and two series would look like one. The table has all "
                "of them.",
            )

    return Chart(spec=_spec(frame, request, x_kind))


#: Words a de-snake-cased column name should not start a sentence with in lowercase.
_ALWAYS_UPPER = {"id", "sku", "vat", "gst", "usd", "eur", "gbp", "myr", "kpi"}


def axis_title(column: str) -> str:
    """A column name in the reader's vocabulary rather than the database's (B-098)."""
    if not column or " " in column:
        return column
    words = [word for word in column.replace("-", "_").split("_") if word]
    if not words:
        return column
    rendered = [word.upper() if word.lower() in _ALWAYS_UPPER else word.lower() for word in words]
    first = rendered[0]
    if first.lower() not in _ALWAYS_UPPER:
        first = first[:1].upper() + first[1:]
    return " ".join([first, *rendered[1:]])


def _plottable(value: object) -> object:
    """One cell, as the spec may carry it (B-103)."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _spec(
    frame: Frame,
    request: ChartRequest,
    x_kind: str,
) -> dict[str, object]:
    """The Vega-Lite spec, built here rather than accepted from the model."""
    # B-098. The axes used to carry the raw column names.
    x: dict[str, object] = {
        "field": request.x,
        "type": x_kind,
        "title": axis_title(request.x),
    }
    if x_kind == "temporal":
        # B-105. A temporal axis with no unit is a continuous one.
        grain = _time_grain(_column_values(frame, request.x))
        if grain is not None:
            x["timeUnit"] = grain
        elif request.mark == "bar":
            # Dates with a time on them, and a bar for each.
            x["type"] = "ordinal"

    encoding: dict[str, object] = {
        "x": x,
        "y": {"field": request.y, "type": "quantitative", "title": axis_title(request.y)},
    }
    if request.series is not None:
        encoding["color"] = {
            "field": request.series,
            "type": "nominal",
            "title": axis_title(request.series),
        }

    spec: dict[str, object] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "mark": request.mark,
        "encoding": encoding,
        # Inline values, never a URL: a spec is rendered in the reader's browser.
        "data": {
            "values": [
                {
                    name: _plottable(row[index])
                    for index, name in enumerate(frame.columns)
                    if index < len(row)
                }
                for row in frame.rows
            ]
        },
    }
    if request.title:
        spec["title"] = request.title
    return spec
