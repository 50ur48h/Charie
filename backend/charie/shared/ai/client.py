"""The AI client: settings, spending check, replays, retries, repair, cost rows."""

import json
import random
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from tenacity import Retrying, retry_if_exception

from charie.shared.ai.cost_log import DbCostLog, MemoryCostLog, usage_row
from charie.shared.ai.errors import (
    AiApiError,
    AiError,
    AiFormError,
    AiOutOfCredit,
    AiReplayMissing,
    AiUnavailable,
    SpendingPaused,
)
from charie.shared.ai.forms import form_schema
from charie.shared.ai.jobs import get_job_settings
from charie.shared.ai.prices import call_cost
from charie.shared.ai.prompts import build_messages, load_prompt
from charie.shared.ai.provider import (
    AiCallError,
    AiReply,
    AiRequest,
    Provider,
    get_provider,
    short_reason,
)
from charie.shared.ai.replay import ReplayStore, default_dir, fingerprint
from charie.shared.ai.spending import spending_state

MAX_RETRIES = 5
BACKOFFS = (1, 2, 4, 8, 16)
MAX_WAIT = 60


class AiClient:
    """One small layer over a provider: `run(job, inputs, form, ...) -> object`."""

    def __init__(
        self,
        provider: Provider | None = None,
        prompts_dir=None,
        sleep=time.sleep,
        cost_log: DbCostLog | MemoryCostLog | None = None,
        replay_mode: str | None = None,
    ) -> None:
        self._provider = provider
        self._prompts_dir = prompts_dir
        self._sleep = sleep
        self._cost_log = cost_log or DbCostLog()
        self._replay_mode = replay_mode

    def provider_for(self, provider_name: str) -> Provider:
        if self._provider is not None:
            return self._provider
        return get_provider(provider_name)

    def replay_mode(self) -> str:
        if self._replay_mode is not None:
            return self._replay_mode
        from charie.shared.config import get_settings

        return get_settings().ai_replay

    def run(
        self,
        job: str,
        inputs: dict[str, Any],
        form: type[BaseModel],
        *,
        app: str,
        message_id: int | None = None,
        learning_run_id: int | None = None,
        knowledge_summary: str | None = None,
        knowledge_version: int | None = None,
    ) -> BaseModel:
        """Run one job: spending check, prompt, replay or call, repair, cost rows."""
        settings = get_job_settings(job)
        limit, warn = self._cost_log.limits()
        spent = self._cost_log.month_spent(datetime.now(UTC))
        if spending_state(spent, limit, warn) == "paused":
            raise SpendingPaused()
        prompt = load_prompt(job, self._prompts_dir)
        messages = build_messages(prompt, inputs, knowledge_summary)
        schema = form_schema(form)
        cache_key = f"{job}:{knowledge_version}" if knowledge_version else job
        request = AiRequest(
            model=settings.model,
            messages=messages,
            form_schema=schema,
            reasoning_effort=settings.reasoning_effort,
            max_output_tokens=settings.max_output_tokens,
            timeout_seconds=settings.timeout_seconds,
            prompt_cache_key=cache_key,
            job=job,
        )
        provider = self.provider_for(settings.provider)
        context = {
            "app": app,
            "message_id": message_id,
            "learning_run_id": learning_run_id,
            "effort": settings.reasoning_effort,
        }
        try:
            started = time.monotonic()
            reply, free = self._attempt(provider, request)
            first_ms = _elapsed_ms(started)
        except (AiUnavailable, AiApiError, AiOutOfCredit) as err:
            self._save_row(request, None, "failed", 0, err.message, context)
            raise
        try:
            obj = form.model_validate(json.loads(reply.content))
        except (ValueError, ValidationError) as err:
            problems = _problems(err)
            self._save_row(request, reply, "retried", first_ms, None, context, free)
            repaired = self._repair(provider, request, reply.content, problems, context)
            try:
                obj = form.model_validate(json.loads(repaired.content))
            except (ValueError, ValidationError):
                self._save_row(request, repaired, "failed", 0, None, context, free)
                raise AiFormError(job) from None
            self._save_row(request, repaired, "ok", 0, None, context, free)
            return obj
        self._save_row(request, reply, "ok", first_ms, None, context, free)
        return obj

    def _attempt(self, provider: Provider, request: AiRequest) -> tuple[AiReply, bool]:
        """One provider call: replayed, recorded, or real — with retries.

        Returns the reply and whether it was free (a replay costs $0).
        """
        mode = self.replay_mode()
        if mode != "off" and getattr(provider, "replayable", False):
            if mode == "replay":
                return self._load_replay(request), True
            outcome = self._complete_with_retries(provider, request)
            self._save_replay(request, outcome.reply)
            return outcome.reply, False
        return self._complete_with_retries(provider, request).reply, False

    def _load_replay(self, request: AiRequest) -> AiReply:
        store = ReplayStore(default_dir())
        digest = fingerprint(_fingerprint_parts(request))
        try:
            record = store.load(request.job, digest)
        except AiReplayMissing:
            raise
        usage = record.get("usage", {})
        return AiReply(
            content=record["content"],
            prompt_tokens=usage.get("prompt_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            reasoning_tokens=usage.get("reasoning_tokens", 0),
            model=request.model,
        )

    def _save_replay(self, request: AiRequest, reply: AiReply) -> None:
        store = ReplayStore(default_dir())
        digest = fingerprint(_fingerprint_parts(request))
        store.save(
            request.job,
            digest,
            {
                "content": reply.content,
                "usage": {
                    "prompt_tokens": reply.prompt_tokens,
                    "cached_tokens": reply.cached_tokens,
                    "completion_tokens": reply.completion_tokens,
                    "reasoning_tokens": reply.reasoning_tokens,
                },
                "recorded_at": datetime.now(UTC).isoformat(),
            },
        )

    def _complete_with_retries(self, provider: Provider, request: AiRequest) -> "_Outcome":
        def should_retry(error: BaseException) -> bool:
            return isinstance(error, AiCallError) and _retryable(error)

        retrying = Retrying(
            stop=_stop_after_retries,
            wait=_wait_for,
            retry=retry_if_exception(should_retry),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            for attempt in retrying:
                with attempt:
                    started = time.monotonic()
                    reply = provider.complete(request)
                    return _Outcome(reply, _elapsed_ms(started))
        except AiCallError as err:
            raise _final_error(request.job, err) from err
        raise AiUnavailable()  # Unreachable: tenacity always raises first.

    def _repair(
        self,
        provider: Provider,
        request: AiRequest,
        bad: str,
        problems: list[str],
        context: dict[str, Any],
    ) -> AiReply:
        _ = context
        detail = "; ".join(problems)
        messages = request.messages + [
            {
                "role": "user",
                "content": (
                    f"Your last reply was:\n{bad}\n\n"
                    f"Your last reply didn't match the required form: {detail}. "
                    "Reply again with JSON that matches the form exactly."
                ),
            }
        ]
        repair_request = AiRequest(
            model=request.model,
            messages=messages,
            form_schema=request.form_schema,
            reasoning_effort=request.reasoning_effort,
            max_output_tokens=request.max_output_tokens,
            timeout_seconds=request.timeout_seconds,
            prompt_cache_key=request.prompt_cache_key,
            job=request.job,
        )
        return self._attempt(provider, repair_request)[0]

    def _save_row(
        self,
        request: AiRequest,
        reply: AiReply | None,
        status: str,
        duration_ms: int,
        error: str | None,
        context: dict[str, Any],
        free: bool = False,
    ) -> None:
        if reply is None or free:
            cost: Decimal = Decimal(0)
            usage = (0, 0, 0, 0)
        else:
            cost = call_cost(
                request.model, reply.prompt_tokens, reply.cached_tokens, reply.completion_tokens
            )
            usage = (
                reply.prompt_tokens,
                reply.cached_tokens,
                reply.completion_tokens,
                reply.reasoning_tokens,
            )
        self._cost_log.add(
            usage_row(
                job=request.job,
                app=context["app"],
                model=request.model,
                prompt_tokens=usage[0],
                cached_tokens=usage[1],
                completion_tokens=usage[2],
                reasoning_tokens=usage[3],
                cost_usd=cost,
                duration_ms=duration_ms,
                status=status,
                message_id=context["message_id"],
                learning_run_id=context["learning_run_id"],
                error=error,
                reasoning_effort=context["effort"],
            )
        )


def get_ai() -> AiClient:
    """A client with the real providers (no call is made yet)."""
    return AiClient()


class _Outcome:
    def __init__(self, reply: AiReply, duration_ms: int) -> None:
        self.reply = reply
        self.duration_ms = duration_ms


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _fingerprint_parts(request: AiRequest) -> dict[str, Any]:
    return {
        "model": request.model,
        "messages": request.messages,
        "schema": request.form_schema,
        "reasoning_effort": request.reasoning_effort,
    }


def _retryable(error: AiCallError) -> bool:
    if error.status is None:
        return True
    return error.status == 429 or error.status >= 500


def _is_out_of_credit(error: AiCallError) -> bool:
    if error.status == 402:
        return True
    text = f"{error.code} {error.message}".lower()
    return "credit" in text or "quota" in text or "billing" in text


def _final_error(job: str, error: AiCallError) -> AiError:
    _ = job
    if _is_out_of_credit(error):
        return AiOutOfCredit()
    if error.status == 401:
        return AiApiError("The Meta API key isn't working. Check META_API_KEY in .env.")
    if _retryable(error):
        return AiUnavailable()
    return AiApiError(short_reason(error) or "the request was refused")


def _problems(error: ValueError | ValidationError) -> list[str]:
    if isinstance(error, ValidationError):
        out = []
        for item in error.errors()[:5]:
            where = ".".join(str(part) for part in item.get("loc", ()))
            out.append(f"{where}: {item.get('msg', 'invalid')}")
        return out or ["the reply didn't match the form"]
    return ["the reply is not JSON"]


def _stop_after_retries(retry_state) -> bool:
    # 1 first try + 5 retries = 6 attempts; stop when the 6th fails.
    return retry_state.attempt_number > MAX_RETRIES


def _wait_for(retry_state) -> float:
    backoff = BACKOFFS[min(retry_state.attempt_number - 1, len(BACKOFFS) - 1)]
    retry_after = 0.0
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, AiCallError) and exc.retry_after:
        retry_after = exc.retry_after
    return min(max(backoff, retry_after) + random.uniform(0, 1), MAX_WAIT)
