"""The business calendar: proposal, confirmation and the P10.3 adapter (P09.4b).

`calendar.business` stores the proposed zone, the week start and the
month the fiscal year starts in. Owner settings and notes are the primary
evidence; without them the entry is a guessed UTC/Monday/January proposal
with a question topic. Confirmation writes the approved zone back to the
setting and retests the time recipes. Periods are inclusive outside and
half-open in SQL; the fiscal year is numbered by the year it starts in.
"""

import re

from sqlalchemy import select

from charie.shared.knowledge.details import CalendarDetails
from charie.shared.knowledge.store import get_entry, list_entries, upsert_entry
from charie.shared.settings import get_setting, set_setting
from charie.shared.tables.sources import OwnerNote

CALENDAR_KEY = "calendar.business"

DEFAULT_CALENDAR = {"time_zone": "UTC", "week_start": "monday", "fiscal_year_start": 1}

_GUESSED_REASON = "Guessed: confirm the zone, week start and fiscal year in questions"

MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)


def _notes_text(session) -> str:
    note = session.scalar(select(OwnerNote).order_by(OwnerNote.id.desc()).limit(1))
    if note is None or not note.text_.strip():
        return ""
    return note.text_


def _week_start_from(notes: str) -> tuple[str, str]:
    """A stated week start and its quote, or Monday with no quote."""
    lowered = notes.lower()
    for day in ("sunday", "monday"):
        match = re.search(rf"\bweek\b.{{0,40}}\b{day}\b|\b{day}\b.{{0,40}}\bweek\b", lowered)
        if match:
            return day, notes[match.start() : match.end()]
    return "monday", ""


def _fiscal_start_from(notes: str) -> tuple[int, str]:
    """A stated fiscal-year month and its quote, or January with no quote."""
    lowered = notes.lower()
    match = re.search(r"fiscal.{0,40}\b(" + "|".join(MONTHS) + r")\b", lowered)
    if match:
        return MONTHS.index(match.group(1)) + 1, notes[match.start() : match.end()]
    return 1, ""


def ensure_calendar(session, version_id: int) -> dict:
    """Create the guessed proposal once; confirmed entries are never touched."""
    old = get_entry(session, version_id, CALENDAR_KEY)
    if old is not None:
        return old.details if isinstance(old.details, dict) else dict(DEFAULT_CALENDAR)
    zone = get_setting(session, "time_zone") or ""
    notes = _notes_text(session)
    week_start, week_quote = _week_start_from(notes)
    fiscal_start, fiscal_quote = _fiscal_start_from(notes)
    evidence = []
    for quote in (week_quote, fiscal_quote):
        if quote:
            evidence.append({"type": "owner_notes", "quote": quote})
    proposed = {
        "time_zone": zone or "UTC",
        "week_start": week_start,
        "fiscal_year_start": fiscal_start,
    }
    upsert_entry(
        session,
        version_id,
        CALENDAR_KEY,
        "calendar",
        "Business calendar",
        "The zone, week start and fiscal year the business uses.",
        proposed,
        "guessed",
        ([{"type": "setting", "text": "time_zone"}] if zone else []) + evidence
        or [{"type": "ai", "text": _GUESSED_REASON}],
        _GUESSED_REASON,
    )
    return proposed


def confirm_calendar(session, version_id: int, values: dict, run) -> dict[str, bool]:
    """Apply the owner's answer: setting, draft and time-recipe retests."""
    from charie.learner.steps import recipes as recipes_step

    checked = CalendarDetails.model_validate(values).model_dump()
    old = get_entry(session, version_id, CALENDAR_KEY)
    before = old.details if old is not None and isinstance(old.details, dict) else {}
    if checked.get("time_zone"):
        set_setting(session, "time_zone", checked["time_zone"])
    upsert_entry(
        session,
        version_id,
        CALENDAR_KEY,
        "calendar",
        "Business calendar",
        "The zone, week start and fiscal year the business uses.",
        checked,
        "confirmed",
        [{"type": "owner_answer", "text": "Confirmed in owner questions."}],
        "Confirmed by the owner.",
    )
    changed = before != checked
    tables = set()
    for entry in list_entries(session, version_id, kinds=["metric"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        column = details.get("time_column") or ""
        table = details.get("table") or ""
        if column and table:
            tables.add(table)
    if changed and tables:
        return recipes_step.retest_affected(session, version_id, sorted(tables), run)
    return {}


def calendar_topics(session, version_id: int) -> list[dict]:
    """The unconfirmed calendar proposal as an owner-question topic."""
    entry = get_entry(session, version_id, CALENDAR_KEY)
    if entry is None or entry.confidence == "confirmed":
        return []
    details = entry.details if isinstance(entry.details, dict) else {}
    return [
        {
            "origin": "calendar",
            "topic": "What calendar the business uses",
            "entry_key": CALENDAR_KEY,
            "affects": [],
            "metric_key": "",
            "context": {
                "word": "calendar",
                "proposed": {
                    "time_zone": details.get("time_zone") or "UTC",
                    "week_start": details.get("week_start") or "monday",
                    "fiscal_year_start": details.get("fiscal_year_start") or 1,
                },
                "alternatives": [],
                "safe": {
                    "time_zone": "UTC",
                    "week_start": "monday",
                    "fiscal_year_start": 1,
                },
            },
        }
    ]


class KbView:
    """One version's knowledge for question time (P09.4b seeds the calendar)."""

    def __init__(self, session, version_id: int) -> None:
        self.session = session
        self.version_id = version_id

    def calendar(self) -> CalendarDetails:
        """The learned calendar, or UTC/Monday/January before learning."""
        entry = get_entry(self.session, self.version_id, CALENDAR_KEY)
        if entry is None or not isinstance(entry.details, dict):
            return CalendarDetails(**DEFAULT_CALENDAR)
        return CalendarDetails.model_validate({**DEFAULT_CALENDAR, **entry.details})
