"""What every model call cost, written down (architecture Part 4.9, 8.3)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from charie.config import Settings, get_settings
from charie.db.models import UsageLedger
from charie.llm.base import Role, Tier, Usage
from charie.tenancy.session import org_session

__all__ = ["Price", "estimate_cost", "price_for", "record"]

STATUS_OK = "ok"
STATUS_ERROR = "error"

#: Prices are quoted per million tokens everywhere in the industry.
TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)

#: Six decimal places, matching ``usage_ledger.cost_usd``.
CENTS = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class Price:
    """USD per million tokens, in and out."""

    input_per_million: Decimal
    output_per_million: Decimal


def price_for(model: str, settings: Settings | None = None) -> Price | None:
    """The configured price for a model, or None if nobody has set one."""
    resolved = settings if settings is not None else get_settings()
    entry = resolved.llm_prices.get(model)
    if not entry:
        return None
    try:
        return Price(
            input_per_million=Decimal(str(entry["input"])),
            output_per_million=Decimal(str(entry["output"])),
        )
    except (KeyError, InvalidOperation):
        # A malformed price is treated as no price.
        return None


def estimate_cost(model: str, usage: Usage, settings: Settings | None = None) -> Decimal | None:
    """What this call cost, or None if the model has no configured price."""
    price = price_for(model, settings)
    if price is None:
        return None
    total = (
        Decimal(usage.input_tokens) * price.input_per_million
        + Decimal(usage.output_tokens) * price.output_per_million
    ) / TOKENS_PER_PRICE_UNIT
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)


async def record(
    *,
    org_id: uuid.UUID,
    role: Role,
    tier: Tier,
    provider: str,
    model: str,
    usage: Usage,
    latency_ms: int,
    run_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    repaired: bool = False,
    error: str | None = None,
    settings: Settings | None = None,
) -> uuid.UUID:
    """Write one ledger row and return its id."""
    async with org_session(org_id) as session:
        row = UsageLedger(
            org_id=org_id,
            run_id=run_id,
            actor_user_id=actor_user_id,
            role=role,
            tier=tier,
            provider=provider,
            model=model,
            status=STATUS_ERROR if error is not None else STATUS_OK,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            tokens_estimated=usage.estimated,
            cost_usd=estimate_cost(model, usage, settings),
            latency_ms=latency_ms,
            repaired=repaired,
            error=error,
        )
        session.add(row)
        await session.flush()
        return row.id
