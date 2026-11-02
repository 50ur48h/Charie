"""Follow-up references, worked out by code: lists, shifts, inherit (P11.2).

The AI only names the parts of a question that point back at the chat
("the second one", "same in Dallas?", "3 months before that"). This
module turns those names into exact filters and periods from the saved
chat context. Anything that cannot be matched is unresolved, and the
answer says so instead of guessing.
"""

import re
from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from charie.chat.analyst.chat_context import ChatContext

from pydantic import BaseModel, Field

from charie.shared.text.numbers import format_period


class ListRef(BaseModel):
    """One pointer at a shown list: words, position and dimension."""

    words: str = Field(default="", description="Your exact words, like 'the second one'.")
    position: int = Field(
        default=1, description="1 for the first item, 2 for the second, -1 for the last."
    )
    dimension: str | None = Field(
        default=None, description="A dimension key, or null when you didn't say which."
    )


class PeriodShift(BaseModel):
    """One move of the chat's last periods: words, unit and steps back."""

    words: str = Field(default="", description="Your exact words, like '3 months before that'.")
    unit: Literal["day", "week", "month", "quarter", "year"] = Field(
        description="The unit to move by."
    )
    n: int = Field(description="Steps to move; below 0 for 'before'.")


class Resolved(BaseModel):
    """The reading with every reference replaced; the panel lines."""

    understanding: object = Field(description="The updated reading.")
    lines: list[str] = Field(default=[], description="One thinking-panel line per resolved part.")


class Unresolved(BaseModel):
    """The first pointer that matched nothing; the reply says so."""

    words: str = Field(default="", description="The exact words that matched nothing.")


#: A `{ref1}`, `{ref2}` or `{ref3}` placeholder in a reading.
REF_RE = re.compile(r"\{ref([1-9])\}")


def ref_numbers(reading: str) -> list[int]:
    """Every ref placeholder number in a reading, in order."""
    return [int(match.group(1)) for match in REF_RE.finditer(reading or "")]


def _whole_month(start: date, end: date) -> bool:
    """A range covering exactly one calendar month."""
    import calendar as pycalendar

    return start.day == 1 and end == date(
        start.year, start.month, pycalendar.monthrange(start.year, start.month)[1]
    )


def _shift_months(start: date, end: date, months: int) -> tuple[date, date]:
    """Move both dates by whole months; a whole month stays a whole month."""
    import calendar as pycalendar

    def _move(day: date) -> date:
        total = (day.year * 12 + (day.month - 1)) + months
        year, month = total // 12, total % 12 + 1
        last = pycalendar.monthrange(year, month)[1]
        return date(year, month, min(day.day, last))

    if _whole_month(start, end):
        total = (start.year * 12 + (start.month - 1)) + months
        year, month = total // 12, total % 12 + 1
        last = pycalendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last)
    return _move(start), _move(end)


def shift_period(start: date, end: date, unit: str, n: int) -> tuple[date, date]:
    """Move a date range back or forward; whole calendar months stay whole."""
    if unit == "day":
        delta = timedelta(days=n)
        return start + delta, end + delta
    if unit == "week":
        delta = timedelta(days=7 * n)
        return start + delta, end + delta
    steps = {"month": 1, "quarter": 3, "year": 12}[unit]
    return _shift_months(start, end, steps * n)


def _metric_name(ask: dict) -> str:
    """The ask in owner words: the metric key, or the new-number words."""
    key = str(ask.get("metric_key") or "")
    if key:
        return key.replace("_", " ")
    return str(ask.get("new_metric") or "what you asked")


def resolve_references(understanding, context: "ChatContext") -> Resolved | Unresolved:
    """Fill inherit, list refs and the period shift from the chat context.

    The understanding is updated in place and returned with one panel
    line per resolved part. The first pointer that matches nothing
    returns unresolved.
    """
    from charie.chat.analyst.dates import PeriodExpression
    from charie.chat.analyst.understand import Ask, Filter  # Late: understand owns the form.

    lines: list[str] = []
    kept: list[str] = []
    focus = context.focus
    inherit = list(getattr(understanding, "inherit", []) or [])
    if "asks" in inherit and not understanding.asks and focus is not None:
        understanding.asks = [Ask(**ask) for ask in focus.asks]
        kept.extend(_metric_name(ask) for ask in focus.asks)
    if "filters" in inherit and focus is not None:
        have = {filt.dimension_key for filt in understanding.filters}
        for raw in focus.filters:
            if raw.get("dimension_key") in have:
                continue
            understanding.filters.append(Filter(**raw))
            kept.extend(str(value) for value in raw.get("values", []))
    if "periods" in inherit and not understanding.periods and focus is not None:
        copied = [
            PeriodExpression.model_validate(period.get("expression", {}))
            for period in focus.periods
            if isinstance(period.get("expression"), dict)
        ]
        understanding.periods = copied
        kept.extend(str(period.get("text", "")) for period in focus.periods)
    for pos, ref in enumerate(getattr(understanding, "list_refs", []) or [], start=1):
        found = _resolve_ref(ref, context)
        if found is None:
            return Unresolved(words=ref.words)
        item, index, title, dimension = found
        understanding.filters = [
            filt for filt in understanding.filters if filt.dimension_key != dimension
        ]
        understanding.filters.append(Filter(dimension_key=dimension, values=[item]))
        understanding.reading = understanding.reading.replace(f"{{ref{pos}}}", f"**{item}**")
        lines.append(f'"{ref.words}" is {item}, number {index + 1} in "{title}".')
    shift = getattr(understanding, "period_shift", None)
    if shift is not None:
        if focus is None or not focus.periods:
            return Unresolved(words=shift.words)
        customs = []
        for period in focus.periods:
            try:
                start = date.fromisoformat(str(period.get("start", "")))
                end = date.fromisoformat(str(period.get("end", "")))
            except ValueError:
                return Unresolved(words=shift.words)
            moved_start, moved_end = shift_period(start, end, shift.unit, shift.n)
            customs.append(PeriodExpression(kind="custom", start=moved_start, end=moved_end))
            shifted = format_period(moved_start.isoformat(), moved_end.isoformat())
            lines.append(f'"{shift.words}" is {shifted}.')
        understanding.periods = customs
    else:
        if kept:
            lines.append("Kept from before: " + "; ".join(kept) + ".")
    return Resolved(understanding=understanding, lines=lines)


def _ref_list(ref: ListRef, context: "ChatContext"):
    """The newest list the ref points at: its dimension, or the newest."""
    lists = list(context.lists)
    if ref.dimension is not None:
        for shown in reversed(lists):
            if shown.dimension == ref.dimension:
                return shown
        return None
    if not lists:
        return None
    return lists[-1]


def _resolve_ref(ref: ListRef, context: "ChatContext") -> tuple[str, int, str, str] | None:
    """The item, its 0-based index, the list title and dimension, or None."""
    shown = _ref_list(ref, context)
    if shown is None:
        return None
    dimension = ref.dimension or shown.dimension
    if dimension is None:
        return None
    index = len(shown.items) - 1 if ref.position == -1 else ref.position - 1
    if index < 0 or index >= len(shown.items):
        return None
    return shown.items[index], index, shown.title, dimension
