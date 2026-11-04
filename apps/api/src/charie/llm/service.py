"""The LLM package's front door."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace

from pydantic import BaseModel

from charie.config import Settings, get_settings
from charie.llm import budget, fallback, meter, registry
from charie.llm.base import (
    CallLimits,
    Completion,
    LLMError,
    LLMProvider,
    LLMRequest,
    Message,
    Role,
    Tags,
    Usage,
)
from charie.llm.registry import ModelChoice
from charie.llm.retry import RetryPolicy
from charie.llm.structured import (
    StructuredOutputError,
    instruction_for,
    parse,
    repair_messages,
)

__all__ = ["complete"]

#: Builds the messages for one provider.
PromptFor = Callable[[LLMProvider], list[Message]]


async def complete(
    *,
    role: Role,
    org_id: uuid.UUID,
    messages: Sequence[Message],
    schema: type[BaseModel] | None = None,
    run_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    limits: CallLimits | None = None,
    retry: RetryPolicy | None = None,
    settings: Settings | None = None,
) -> Completion:
    """Call the model configured for ``role``, meter it, and return what it said."""
    resolved = settings if settings is not None else get_settings()
    chain = registry.resolve(role, resolved)
    tags = Tags(org_id=org_id, role=role, run_id=run_id, actor_user_id=actor_user_id)
    call_limits = limits if limits is not None else CallLimits()
    base = list(messages)

    def first_prompt(provider: LLMProvider) -> list[Message]:
        return _with_schema_instruction(base, schema, provider)

    def attempt_for(
        prompt_for: PromptFor, *, repaired: bool
    ) -> Callable[[ModelChoice], Awaitable[Completion]]:
        async def attempt(choice: ModelChoice) -> Completion:
            provider = registry.get_provider(choice.provider, resolved)
            # Before the call: a ceiling enforced afterwards is a report.
            await budget.assert_within_limit(
                org_id=org_id, run_id=run_id, model=choice.model, settings=resolved
            )
            request = LLMRequest(
                model=choice.model,
                messages=prompt_for(provider),
                tags=tags,
                schema=schema,
                limits=call_limits,
            )
            return await _call(provider, request, choice, resolved, repaired=repaired)

        return attempt

    completion = await fallback.walk(
        chain,
        attempt_for(first_prompt, repaired=False),
        policy=retry,
    )
    if schema is None:
        return completion

    try:
        return replace(completion, parsed=parse(schema, completion.text))
    except StructuredOutputError as first:
        # Bound to a local before the closure.
        problem = str(first)

        def repair_prompt(provider: LLMProvider) -> list[Message]:
            return repair_messages(
                first_prompt(provider),
                reply=completion.text,
                problem=problem,
                schema=schema,
            )

        second = await fallback.walk(
            chain,
            attempt_for(repair_prompt, repaired=True),
            policy=retry,
        )
        try:
            parsed = parse(schema, second.text)
        except StructuredOutputError as final:
            # Both attempts named, because the pair is the diagnosis.
            raise StructuredOutputError(
                f"{second.model} did not produce valid {schema.__name__} in two "
                f"attempts. First: {problem}. After repair: {final}."
            ) from None
        return replace(second, parsed=parsed, repaired=True)


async def _call(
    provider: LLMProvider,
    request: LLMRequest,
    choice: ModelChoice,
    settings: Settings,
    *,
    repaired: bool,
) -> Completion:
    """One provider call, timed and metered whichever way it ends."""
    started = time.monotonic()
    try:
        completion = await provider.complete(request)
    except LLMError as error:
        # Tokens are unknown on a failure — the provider did not report any.
        await meter.record(
            org_id=request.tags.org_id,
            role=choice.role,
            tier=choice.tier,
            provider=choice.provider,
            model=choice.model,
            usage=Usage(),
            latency_ms=_elapsed_ms(started),
            run_id=request.tags.run_id,
            actor_user_id=request.tags.actor_user_id,
            repaired=repaired,
            error=str(error),
            settings=settings,
        )
        raise

    latency_ms = _elapsed_ms(started)
    await meter.record(
        org_id=request.tags.org_id,
        role=choice.role,
        tier=choice.tier,
        provider=choice.provider,
        model=completion.model,
        usage=completion.usage,
        latency_ms=latency_ms,
        run_id=request.tags.run_id,
        actor_user_id=request.tags.actor_user_id,
        repaired=repaired,
        settings=settings,
    )
    return replace(completion, latency_ms=latency_ms)


def _with_schema_instruction(
    messages: list[Message], schema: type[BaseModel] | None, provider: LLMProvider
) -> list[Message]:
    """Add the "reply with JSON like this" instruction, when it is needed."""
    if schema is None or provider.capabilities().supports_response_schema:
        return messages
    boundary = next(
        (index for index, message in enumerate(messages) if message.role != "system"),
        len(messages),
    )
    return [*messages[:boundary], instruction_for(schema), *messages[boundary:]]


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
