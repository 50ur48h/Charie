"""Walking the chain (architecture Part 4.9, 8.5)."""

from __future__ import annotations

import pytest

from charie.llm import fallback
from charie.llm.base import Completion, LLMError, Usage
from charie.llm.registry import ModelChoice
from charie.llm.retry import RetryPolicy

PRIMARY = ModelChoice(role="plan", tier="strong", provider="first", model="first-strong")
SECOND = ModelChoice(role="plan", tier="strong", provider="second", model="second-strong")

NO_WAIT = RetryPolicy(attempts=2, base_delay=0.0)


def answer(choice: ModelChoice) -> Completion:
    return Completion(
        text="ok",
        model=choice.model,
        provider=choice.provider,
        usage=Usage(1, 1),
        latency_ms=0,
    )


async def sleep_nothing(seconds: float) -> None:
    return None


async def walk(chain: list[ModelChoice], attempt: object) -> Completion:
    return await fallback.walk(
        chain,
        attempt,  # pyright: ignore[reportArgumentType]
        policy=NO_WAIT,
        sleep=sleep_nothing,
        jitter=lambda: 0.0,
    )


async def test_the_primary_answers_and_nothing_else_is_touched() -> None:
    tried: list[str] = []

    async def attempt(choice: ModelChoice) -> Completion:
        tried.append(choice.provider)
        return answer(choice)

    completion = await walk([PRIMARY, SECOND], attempt)

    assert completion.provider == "first"
    assert tried == ["first"]


async def test_an_injected_429_moves_to_the_next_provider() -> None:
    """The gate's fallback criterion."""
    tried: list[str] = []

    async def attempt(choice: ModelChoice) -> Completion:
        tried.append(choice.provider)
        if choice.provider == "first":
            raise LLMError("the provider returned 429: rate_limit_exceeded", retryable=True)
        return answer(choice)

    completion = await walk([PRIMARY, SECOND], attempt)

    assert completion.provider == "second"
    assert completion.model == "second-strong"
    # Retried on the primary before moving on: two attempts there, then one that worked.
    assert tried == ["first", "first", "second"]


async def test_a_non_retryable_failure_stops_the_chain_where_it_is() -> None:
    """A 400 is our bug. It will be just as wrong at the next provider."""
    tried: list[str] = []

    async def attempt(choice: ModelChoice) -> Completion:
        tried.append(choice.provider)
        raise LLMError("the provider returned 400: bad_request", retryable=False)

    with pytest.raises(LLMError, match="400"):
        await walk([PRIMARY, SECOND], attempt)

    assert tried == ["first"]


async def test_a_chain_that_all_fails_raises_the_last_failure() -> None:
    async def attempt(choice: ModelChoice) -> Completion:
        raise LLMError(f"{choice.provider} is down", retryable=True)

    with pytest.raises(LLMError, match="second is down"):
        await walk([PRIMARY, SECOND], attempt)


async def test_a_single_provider_chain_still_retries() -> None:
    """With one provider configured there is nowhere to fall back to."""
    tried = 0

    async def attempt(choice: ModelChoice) -> Completion:
        nonlocal tried
        tried += 1
        if tried == 1:
            raise LLMError("429", retryable=True)
        return answer(choice)

    completion = await walk([PRIMARY], attempt)

    assert completion.provider == "first"
    assert tried == 2


async def test_an_empty_chain_is_refused_rather_than_returning_nothing() -> None:
    async def attempt(choice: ModelChoice) -> Completion:
        raise AssertionError("must not be called")

    with pytest.raises(LLMError, match="no model chain"):
        await walk([], attempt)
