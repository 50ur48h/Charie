"""A ceiling on what one run may spend."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text

from charie.config import Settings, get_settings
from charie.llm.base import LLMError
from charie.llm.meter import price_for
from charie.tenancy.session import org_session

__all__ = ["RunCostExceededError", "RunSpend", "assert_within_limit", "spent_on_run"]


class RunCostExceededError(LLMError):
    """This run has spent what it was allowed to spend."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


class RunSpend:
    """What one run has cost so far, and how much of that is actually known."""

    __slots__ = ("unpriced_calls", "usd")

    def __init__(self, usd: Decimal, unpriced_calls: int) -> None:
        self.usd = usd
        self.unpriced_calls = unpriced_calls

    def __repr__(self) -> str:
        return f"RunSpend(usd={self.usd}, unpriced_calls={self.unpriced_calls})"


_SPEND = text(
    "SELECT COALESCE(SUM(cost_usd), 0) AS usd, "
    "COUNT(*) FILTER (WHERE cost_usd IS NULL) AS unpriced "
    "FROM usage_ledger WHERE run_id = :run"
)


async def spent_on_run(org_id: uuid.UUID, run_id: uuid.UUID) -> RunSpend:
    """Sum this run's ledger rows. Scoped by RLS to the organization asking."""
    async with org_session(org_id) as session:
        row = (await session.execute(_SPEND, {"run": run_id})).mappings().one()
        return RunSpend(usd=Decimal(str(row["usd"])), unpriced_calls=int(row["unpriced"]))


async def assert_within_limit(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID | None,
    model: str,
    settings: Settings | None = None,
) -> None:
    """Refuse the next call when this run has reached its ceiling."""
    resolved = settings if settings is not None else get_settings()
    limit = resolved.llm_run_cost_limit_usd
    if limit is None or run_id is None:
        return

    if resolved.llm_refuse_unpriced_when_capped and price_for(model, resolved) is None:
        raise RunCostExceededError(
            f"{model!r} has no entry in LLM_PRICES, so its spend cannot be counted "
            f"against this run's ${limit:.2f} ceiling. Price the model, or set "
            "LLM_REFUSE_UNPRICED_WHEN_CAPPED=false to accept an uncounted cost."
        )

    spend = await spent_on_run(org_id, run_id)

    if resolved.llm_refuse_unpriced_when_capped and spend.unpriced_calls:
        raise RunCostExceededError(
            f"this run has {spend.unpriced_calls} call(s) with an unknown cost, so "
            f"its ${limit:.2f} ceiling cannot be enforced honestly. Price every "
            "model it uses, or set LLM_REFUSE_UNPRICED_WHEN_CAPPED=false."
        )

    if spend.usd >= Decimal(str(limit)):
        raise RunCostExceededError(
            f"this run has spent ${spend.usd:.4f} of its ${limit:.2f} ceiling and "
            "will not make further model calls. Raise LLM_RUN_COST_LIMIT_USD, or "
            "treat what it has as the answer."
        )
