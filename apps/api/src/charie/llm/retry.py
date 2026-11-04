"""Trying again, the same way for every provider (architecture Part 8.5)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from charie.llm.base import LLMError

__all__ = ["RetryPolicy", "with_retries"]


class RetryPolicy:
    """How many times, and how long to wait (architecture 8.5's three attempts)."""

    __slots__ = ("attempts", "base_delay", "max_delay")

    def __init__(self, attempts: int = 3, base_delay: float = 0.5, max_delay: float = 8.0) -> None:
        if attempts < 1:
            raise ValueError("attempts must be at least 1: a policy that never calls is not one")
        self.attempts = attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def delay_for(self, attempt: int, jitter: float) -> float:
        """Seconds to wait before attempt ``attempt`` (1-based, so never called with 1)."""
        exponential = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        return exponential * (0.5 + jitter)


async def with_retries[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Run ``operation``, retrying only what the provider marked retryable."""
    resolved = policy if policy is not None else RetryPolicy()
    last: LLMError | None = None

    for attempt in range(1, resolved.attempts + 1):
        try:
            return await operation()
        except LLMError as error:
            if not error.retryable:
                raise
            last = error
            if attempt < resolved.attempts:
                await sleep(resolved.delay_for(attempt, jitter()))

    # Unreachable unless attempts < 1, which the constructor refuses.
    assert last is not None  # noqa: S101 — narrowing for the type checker
    raise last
