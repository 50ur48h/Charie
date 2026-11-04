"""What periods this database can speak about, and whether an answer stayed inside them."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "TIME_TYPES",
    "Asked",
    "Coverage",
    "Period",
    "asked_for",
    "available_period",
    "coverage_note",
    "describe",
    "held_days",
    "limitation",
    "period_of_values",
]

#: Column types whose low/high is a period rather than a magnitude.
TIME_TYPES: tuple[str, ...] = ("date", "timestamp", "datetime", "smalldatetime", "time")

#: A year and a month, which is the finest grain both sides can honestly express.
_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])(?:-\d{2})?(?:[ T][\d:.+\-]*)?$")


@dataclass(frozen=True, slots=True)
class Period:
    """A closed range of months, as ``YYYY-MM``."""

    earliest: str
    latest: str

    def __str__(self) -> str:
        return (
            self.earliest if self.earliest == self.latest else f"{self.earliest} to {self.latest}"
        )

    def contains(self, other: Period) -> bool:
        return self.earliest <= other.earliest and other.latest <= self.latest


@dataclass(frozen=True, slots=True)
class Coverage:
    """The verdict, and enough of the measurement to argue with it."""

    status: str
    reason: str = ""
    answered: Period | None = None
    available: Period | None = None

    def as_payload(self) -> dict[str, object]:
        """For the trace. The reason travels with the status."""
        return {
            "status": self.status,
            "reason": self.reason,
            "answered": str(self.answered) if self.answered else None,
            "available": str(self.available) if self.available else None,
        }


def _month(value: object) -> str | None:
    """``YYYY-MM`` from anything that starts with one, else None."""
    if value is None:
        return None
    match = _MONTH.match(str(value).strip())
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _span(values: Sequence[object]) -> Period | None:
    months = sorted(month for value in values if (month := _month(value)) is not None)
    return Period(earliest=months[0], latest=months[-1]) if months else None


def available_period(columns: Sequence[tuple[str, str | None, str | None]]) -> Period | None:
    """The widest period the catalog records, over ``(data_type, min, max)``."""
    ends: list[object] = []
    for data_type, minimum, maximum in columns:
        if not any(kind in data_type.lower() for kind in TIME_TYPES):
            continue
        ends.extend(value for value in (minimum, maximum) if value is not None)
    return _span(ends)


def period_of_values(values: Sequence[object], *, truncated: bool) -> tuple[Period | None, str]:
    """The period a result covers, or the reason it cannot be said."""
    if truncated:
        return None, "the result was cut off at the row limit, so its last period is not its latest"
    period = _span(values)
    if period is None:
        return None, "no column in the result held a recognisable year and month"
    return period, ""


def describe(answered: Period | None, available: Period | None, *, reason: str = "") -> Coverage:
    """Compare the two measurements, or say why there was nothing to compare."""
    if reason:
        return Coverage(status="abstained", reason=reason, answered=answered, available=available)
    if available is None:
        return Coverage(
            status="abstained",
            reason="no dated column in this database has been profiled, so there is nothing to "
            "compare against",
            answered=answered,
        )
    if answered is None:
        return Coverage(
            status="abstained",
            reason="the answer rests on no result with a recognisable period",
            available=available,
        )
    if available.contains(answered):
        return Coverage(status="contained", answered=answered, available=available)
    return Coverage(status="outside", answered=answered, available=available)


def coverage_note(available: Period | None, asked: Asked | None = None) -> str:
    """What the planner is told as fact (architecture 4.3), or nothing."""
    if asked is not None and asked.held is not None and asked.asked is not None:
        low, high = asked.held
        first, last = asked.asked[0], _before(asked.asked[1])
        if asked.verdict == "none":
            return (
                f"The question asks about {first} to {last}. This database holds "
                f"{low} to {high}, so **none** of the period asked for exists here. Say that "
                f"plainly and name both periods. Do not report a zero: no rows and no data are "
                f"different answers, and only one of them is true."
            )
        if asked.verdict == "partial" and asked.overlap is not None:
            begin, until = asked.overlap
            return (
                f"The question asks about {first} to {last}. This database holds {low} to "
                f"{high}, so only {begin} to {until} of it exists. Answer for the part that "
                f"exists and say which part does not — **narrowing to the data is correct here, "
                f"not a compromise**, and an answer that queries past {high} is describing rows "
                f"that are not there."
            )
    if available is None:
        return ""
    return (
        f"The dated columns in this database's catalogued tables run from "
        f"{available.earliest} to {available.latest}. That is what has been measured, not a "
        f"limit on what you may ask: a table whose period column is text has no measured "
        f"range and is not represented here. Do not tell the reader a period is missing "
        f"without checking it against this."
    )


def limitation(coverage: Coverage) -> str:
    """The sentence a reader gets, and only for ``outside``."""
    if coverage.status != "outside" or coverage.answered is None or coverage.available is None:
        return ""
    return (
        f"This answer covers {coverage.answered}, which is outside the period the catalog "
        f"records for this database's dated columns ({coverage.available}). Either it rests on "
        f"a table whose period column has no measured range, or it reaches beyond the data "
        f"that was profiled — both are worth checking before relying on the figures."
    )


# --- The period a question asked for, against the period the data holds (D-051) ---

#: A full ISO date, which is what a profiled `date` column stores and what `critic.stated_range`...
_DAY = re.compile(r"^(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True, slots=True)
class Asked:
    """What a question wanted, against what the catalog holds."""

    verdict: str
    asked: tuple[str, str] | None = None
    held: tuple[str, str] | None = None
    overlap: tuple[str, str] | None = None


def _day(value: object) -> str | None:
    if value is None:
        return None
    match = _DAY.match(str(value).strip())
    return match.group(1) if match else None


def held_days(columns: Sequence[tuple[str, str | None, str | None]]) -> tuple[str, str] | None:
    """The widest span of full dates the catalog records, at day precision."""
    ends: list[str] = []
    for data_type, minimum, maximum in columns:
        if not any(kind in data_type.lower() for kind in TIME_TYPES):
            continue
        ends.extend(day for value in (minimum, maximum) if (day := _day(value)) is not None)
    if not ends:
        return None
    ends.sort()
    return ends[0], ends[-1]


def asked_for(wanted: tuple[str, str] | None, held: tuple[str, str] | None) -> Asked:
    """Compare the period a question named with the period the data holds."""
    if wanted is None or held is None:
        return Asked(verdict="unknown", asked=wanted, held=held)
    start, end_exclusive = wanted
    low, high = held
    # `high` is the last day that exists; the asked range ends the day before `end_exclusive`.
    last_asked = min(_before(end_exclusive), high)
    first_asked = max(start, low)
    if first_asked > last_asked:
        return Asked(verdict="none", asked=wanted, held=held)
    if start >= low and _before(end_exclusive) <= high:
        return Asked(
            verdict="covered", asked=wanted, held=held, overlap=(start, _before(end_exclusive))
        )
    return Asked(verdict="partial", asked=wanted, held=held, overlap=(first_asked, last_asked))


def _before(day: str) -> str:
    """The day before an exclusive end, as ISO text."""
    from datetime import date as _date

    return _date.fromordinal(_date.fromisoformat(day).toordinal() - 1).isoformat()
