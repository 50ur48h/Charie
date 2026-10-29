"""The cost log: one `ai_calls` row per reply (03, 05 section 7)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from charie.shared.db import session_scope
from charie.shared.tables.usage import AiCall


class DbCostLog:
    """Writes `ai_calls` rows in its own short transaction."""

    def add(self, row: dict[str, Any]) -> None:
        with session_scope() as session:
            session.add(AiCall(**row))

    def month_spent(self, now: datetime) -> Decimal:
        from charie.shared.ai.spending import month_spent

        with session_scope() as session:
            return month_spent(session, now)

    def limits(self) -> tuple[float, float]:
        from charie.shared.settings import get_setting

        with session_scope() as session:
            return (
                get_setting(session, "spend_limit_usd"),
                get_setting(session, "spend_warn_percent"),
            )


class MemoryCostLog:
    """Keeps rows in memory, for unit tests."""

    def __init__(
        self,
        limit: float = 150,
        warn_percent: float = 80,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows: list[dict[str, Any]] = list(rows) if rows else []
        self._limit = limit
        self._warn_percent = warn_percent

    def add(self, row: dict[str, Any]) -> None:
        self.rows.append(row)

    def month_spent(self, now: datetime) -> Decimal:
        from charie.shared.ai.spending import month_spent_rows

        return month_spent_rows(self.rows, now)

    def limits(self) -> tuple[float, float]:
        return (self._limit, self._warn_percent)


def usage_row(
    *,
    at=None,
    job: str,
    app: str,
    model: str,
    prompt_tokens: int,
    cached_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
    cost_usd: Decimal,
    duration_ms: int,
    status: str,
    message_id: int | None = None,
    learning_run_id: int | None = None,
    error: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """One `ai_calls` row (keys match the table exactly)."""
    return {
        "at": at or datetime.now(UTC),
        "app": app,
        "job": job,
        "provider": "meta",
        "model": model,
        "reasoning_effort": reasoning_effort,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cost_usd": cost_usd,
        "duration_ms": duration_ms,
        "status": status,
        "message_id": message_id,
        "learning_run_id": learning_run_id,
        "error": error,
    }
