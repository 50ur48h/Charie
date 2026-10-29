"""Prices: dollars per 1M tokens, checked 27 Oct 2026 (03, meta-api.md)."""

from decimal import Decimal

from charie.shared.ai.errors import AiError

# (input, cached input, output) dollars per 1M tokens.
PRICES: dict[str, tuple[str, str, str]] = {
    "muse-wonder-1.0": ("4.00", "0.20", "20.00"),
}

_MILLION = Decimal(1_000_000)


def call_cost(
    model: str, prompt_tokens: int, cached_tokens: int, completion_tokens: int
) -> Decimal:
    """The price of one call. Reasoning tokens are inside `completion_tokens`."""
    if model not in PRICES:
        raise AiError(
            "unknown_price",
            f"No price is known for model `{model}`. Add it to charie/shared/ai/prices.py.",
        )
    full_in, cached_in, out = (Decimal(price) for price in PRICES[model])
    return (
        (Decimal(prompt_tokens - cached_tokens) * full_in)
        + (Decimal(cached_tokens) * cached_in)
        + (Decimal(completion_tokens) * out)
    ) / _MILLION
