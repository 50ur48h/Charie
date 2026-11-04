"""Walking the provider chain (architecture Part 4.9, 8.5)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from functools import partial

from charie.llm.base import Completion, LLMError
from charie.llm.registry import ModelChoice
from charie.llm.retry import RetryPolicy, with_retries

__all__ = ["walk"]


async def walk(
    chain: Sequence[ModelChoice],
    attempt: Callable[[ModelChoice], Awaitable[Completion]],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[], float] = random.random,
) -> Completion:
    """The first completion the chain can produce."""
    if not chain:
        raise LLMError("no model chain to call: resolve returned nothing", retryable=False)

    last: LLMError | None = None
    for choice in chain:
        try:
            return await with_retries(
                partial(attempt, choice), policy=policy, sleep=sleep, jitter=jitter
            )
        except LLMError as error:
            if not error.retryable:
                raise
            last = error

    assert last is not None  # noqa: S101 — the loop ran at least once
    raise last
