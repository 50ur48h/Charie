"""Spending: this calendar month's AI total, in the owner's time zone (03)."""

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo


def as_utc(moment: datetime) -> datetime:
    """Naive times count as UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def month_bounds(now: datetime, time_zone: str | None) -> tuple[datetime, datetime]:
    """This month as UTC instants: local midnight on the 1st to next month."""
    zone = ZoneInfo(time_zone) if time_zone else UTC
    local = as_utc(now).astimezone(zone)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.astimezone(UTC), end.astimezone(UTC)


def _row_month(row_time: datetime, time_zone: str | None) -> tuple[int, int]:
    zone = ZoneInfo(time_zone) if time_zone else UTC
    return as_utc(row_time).astimezone(zone).timetuple()[:2]


def _target_month(now: datetime, time_zone: str | None) -> tuple[int, int]:
    zone = ZoneInfo(time_zone) if time_zone else UTC
    return as_utc(now).astimezone(zone).timetuple()[:2]


def month_spent_rows(
    rows: Iterable[dict[str, Any]], now: datetime, time_zone: str | None = None
) -> Decimal:
    """Sum `cost_usd` for rows in this calendar month (memory rows)."""
    total = Decimal(0)
    target = _target_month(now, time_zone)
    for row in rows:
        if _row_month(row["at"], time_zone) == target:
            total += Decimal(row["cost_usd"])
    return total


def month_spent(session, now: datetime) -> Decimal:
    """Sum `ai_calls.cost_usd` for this calendar month, in the set time zone."""
    from sqlalchemy import func, select

    from charie.shared.settings import get_setting
    from charie.shared.tables.usage import AiCall

    time_zone = get_setting(session, "time_zone")
    start, end = month_bounds(now, time_zone)
    total = session.scalar(
        select(func.coalesce(func.sum(AiCall.cost_usd), 0)).where(
            AiCall.at >= start, AiCall.at < end
        )
    )
    return Decimal(total)


def spending_state(spent: float | Decimal, limit: float, warn_percent: float) -> str:
    """`paused` at the limit, `warn` at the warning level, else `ok`."""
    spent = float(spent)
    if spent >= limit:
        return "paused"
    if spent >= limit * warn_percent / 100:
        return "warn"
    return "ok"
