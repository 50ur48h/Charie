"""The per-question view of one knowledge version (P10.3).

The rest of the analyst reads through here instead of the raw entries:
recipes, periods and every later helper see the same grouped knowledge.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.chat.analyst.dates import DateContext
from charie.shared.knowledge.details import CalendarDetails, DefaultDetails
from charie.shared.knowledge.store import list_entries
from charie.shared.settings import get_setting
from charie.shared.tables.sources import DataSource


def _as_date(value: object) -> date | None:
    """An ISO string or date/datetime as a date; anything else is empty."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


class KbView:
    """One version's entries, read once and grouped by kind."""

    def __init__(
        self, entries: dict[str, dict], raw: dict[str, dict], data_through: date | None
    ) -> None:
        self._entries = entries
        self._raw = raw
        self._data_through = data_through

    @classmethod
    def load(cls, session: Session, version_id: int) -> "KbView":
        """Read every entry of one version once (through `list_entries`)."""
        entries: dict[str, dict] = {}
        raw: dict[str, dict] = {}
        for entry in list_entries(session, version_id):
            details = entry.details if isinstance(entry.details, dict) else {}
            entries.setdefault(entry.kind, {})[entry.key] = details
            raw[entry.key] = details
        row = session.scalar(select(DataSource).order_by(DataSource.id.desc()).limit(1))
        through = _as_date(row.data_through) if row is not None else None
        return cls(entries, raw, through)

    @property
    def data_through(self) -> date | None:
        """The date the customer data ends, if a source is connected."""
        return self._data_through

    def metrics(self) -> dict[str, dict]:
        """Metric key to its recipe details."""
        return dict(self._entries.get("metric", {}))

    def dimensions(self) -> dict[str, dict]:
        """Dimension key to its details."""
        return dict(self._entries.get("dimension", {}))

    def defaults(self) -> dict[str, DefaultDetails]:
        """Default word to its meaning (for vague words like "last week")."""
        found: dict[str, DefaultDetails] = {}
        for details in self._entries.get("default", {}).values():
            parsed = DefaultDetails.model_validate(details)
            if parsed.word:
                found[parsed.word] = parsed
        return found

    def names(self) -> dict[str, dict]:
        """Name key to its details (what the owner calls things)."""
        return dict(self._entries.get("name", {}))

    def rules(self) -> dict[str, dict]:
        """Rule key to its details (hard rules the answers must obey)."""
        return dict(self._entries.get("rule", {}))

    def styles(self) -> dict[str, dict]:
        """Style key to its details (words the answers reuse)."""
        return dict(self._entries.get("style", {}))

    def calendar(self) -> CalendarDetails:
        """The business calendar; empty when nothing was learned."""
        raw = self.calendar_raw()
        if raw is not None:
            return CalendarDetails.model_validate(raw)
        return CalendarDetails()

    def calendar_raw(self) -> dict | None:
        """The calendar entry's raw details, for exact-match reads."""
        for details in self._entries.get("calendar", {}).values():
            return details
        return None

    def data_from(self) -> date | None:
        """The earliest activity start: the big tables, not small lists.

        Only `data_range` entries whose `date_to` equals `data_through`
        count; snapshot and list ranges end elsewhere. Empty when none.
        """
        if self._data_through is None:
            return None
        earliest: date | None = None
        for details in self._entries.get("data_range", {}).values():
            if _as_date(details.get("date_to")) != self._data_through:
                continue
            start = _as_date(details.get("date_from"))
            if start is not None and (earliest is None or start < earliest):
                earliest = start
        return earliest


def load_date_context(session: Session, ctx, kb: KbView) -> DateContext:
    """The resolver's inputs: today in the zone, the data window, the calendar.

    The week start and fiscal start read exactly as `load_build_context`
    does; the time zone is the `time_zone` setting (`UTC` if empty).
    """
    _ = ctx
    zone = get_setting(session, "time_zone") or "UTC"
    today = datetime.now(ZoneInfo(zone)).date()
    calendar_details = kb.calendar_raw() or {}
    week_start = "sunday" if calendar_details.get("week_start") == "sunday" else "monday"
    try:
        fiscal_start_month = int(calendar_details.get("fiscal_year_start") or 1)
    except (TypeError, ValueError):
        fiscal_start_month = 1
    return DateContext(
        today=today,
        data_through=kb.data_through,
        data_from=kb.data_from(),
        week_start=week_start,
        fiscal_start_month=fiscal_start_month,
        time_zone=zone,
    )
