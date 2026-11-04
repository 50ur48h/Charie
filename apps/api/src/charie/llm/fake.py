"""A model that answers from a script, and remembers everything it was asked."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Self

from pydantic import BaseModel

from charie.llm.base import (
    ROLES,
    Completion,
    LLMError,
    LLMRequest,
    ProviderCaps,
    Role,
    Usage,
    estimate_tokens,
)

__all__ = ["FakeLLM", "NoScriptedResponseError", "RecordedCall", "Script"]

#: What a fake completion reports as its model when a test does not care.
STUB_MODEL = "fake-model"


class NoScriptedResponseError(LLMError):
    """Nothing in the script matched the request that arrived."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


@dataclass(frozen=True, slots=True)
class Script:
    """One scripted answer and the requests it applies to."""

    #: The reply text. A callable receives the request.
    respond: str | Callable[[LLMRequest], str] = ""
    role: Role | None = None
    #: Matched against the whole prompt, case-sensitively.
    contains: str | None = None
    #: Raised instead of answering. For exercising retry, fallback and the refusal paths.
    raises: LLMError | None = None
    #: How many times this script may match, or None for unlimited.
    times: int | None = None
    #: Overrides the token estimate, for tests about metering and cost.
    usage: Usage | None = None
    finish_reason: str = "stop"

    def matches(self, request: LLMRequest) -> bool:
        if self.role is not None and request.tags.role != self.role:
            return False
        return self.contains is None or self.contains in request.prompt_text


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """One call, kept whole."""

    request: LLMRequest
    completion: Completion | None
    error: LLMError | None = None

    @property
    def role(self) -> Role:
        return self.request.tags.role

    @property
    def model(self) -> str:
        return self.request.model

    @property
    def prompt(self) -> str:
        return self.request.prompt_text

    @property
    def system_prompt(self) -> str:
        return self.request.text_of("system")

    @property
    def user_prompt(self) -> str:
        return self.request.text_of("user")


@dataclass(eq=False)
class FakeLLM:
    """A provider whose answers are written in advance."""

    scripts: list[Script] = field(default_factory=list[Script])
    #: Answered when no script matches.
    default: str | None = None
    model_name: str = STUB_MODEL

    _calls: list[RecordedCall] = field(default_factory=list[RecordedCall], init=False, repr=False)
    _used: dict[int, int] = field(default_factory=dict[int, int], init=False, repr=False)

    # -- scripting ---------------------------------------------------------

    def script(
        self,
        respond: str | Callable[[LLMRequest], str] = "",
        *,
        role: Role | None = None,
        contains: str | None = None,
        raises: LLMError | None = None,
        times: int | None = None,
        usage: Usage | None = None,
        finish_reason: str = "stop",
    ) -> Self:
        """Append one script and return self, so calls chain in a fixture."""
        self.scripts.append(
            Script(
                respond=respond,
                role=role,
                contains=contains,
                raises=raises,
                times=times,
                usage=usage,
                finish_reason=finish_reason,
            )
        )
        return self

    def script_json(
        self,
        payload: BaseModel | Mapping[str, object],
        *,
        role: Role | None = None,
        contains: str | None = None,
        times: int | None = None,
    ) -> Self:
        """Script a structured reply from an object rather than from a string."""
        text = (
            payload.model_dump_json()
            if isinstance(payload, BaseModel)
            else json.dumps(dict(payload), sort_keys=True)
        )
        return self.script(text, role=role, contains=contains, times=times)

    @classmethod
    def from_mapping(cls, entries: Sequence[Mapping[str, object]]) -> FakeLLM:
        """Build from plain data — a fixture file in whatever format the caller parsed."""
        fake = cls()
        for entry in entries:
            respond = entry.get("respond", "")
            role = entry.get("role")
            contains = entry.get("contains")
            times = entry.get("times")
            if role is not None and role not in ROLES:
                raise ValueError(f"{role!r} is not an LLM role. Roles are {list(ROLES)}.")
            fake.script(
                respond if isinstance(respond, str) else json.dumps(respond, sort_keys=True),
                role=role,
                contains=contains if isinstance(contains, str) else None,
                times=times if isinstance(times, int) else None,
            )
        return fake

    def reset(self) -> None:
        """Forget every call and every use count. Scripts stay."""
        self._calls.clear()
        self._used.clear()

    # -- the provider protocol --------------------------------------------

    def capabilities(self) -> ProviderCaps:
        return ProviderCaps(
            name="fake",
            # False on purpose: the fake exercises the harder path.
            supports_response_schema=False,
            is_stub=True,
        )

    async def complete(self, request: LLMRequest) -> Completion:
        script = self._match(request)
        if script is None:
            error = NoScriptedResponseError(self._unmatched_message(request))
            self._calls.append(RecordedCall(request=request, completion=None, error=error))
            raise error

        if script.raises is not None:
            self._calls.append(RecordedCall(request=request, completion=None, error=script.raises))
            raise script.raises

        text = script.respond(request) if callable(script.respond) else script.respond
        completion = Completion(
            text=text,
            model=request.model or self.model_name,
            provider="fake",
            usage=script.usage
            or Usage(
                input_tokens=estimate_tokens(request.prompt_text),
                output_tokens=estimate_tokens(text),
                estimated=True,
            ),
            # Fixed, not measured: a duration that varies is a duration a test cannot assert on.
            latency_ms=0,
            finish_reason=script.finish_reason,
        )
        self._calls.append(RecordedCall(request=request, completion=completion))
        return completion

    async def aclose(self) -> None:
        """Nothing to close. Defined because the protocol says every caller owes a provider this."""

    # -- recording ---------------------------------------------------------

    @property
    def calls(self) -> tuple[RecordedCall, ...]:
        """Every call, in order — including the ones that raised."""
        return tuple(self._calls)

    def calls_for(self, role: Role) -> tuple[RecordedCall, ...]:
        return tuple(call for call in self._calls if call.role == role)

    def last_call(self, role: Role | None = None) -> RecordedCall:
        candidates = self._calls if role is None else list(self.calls_for(role))
        if not candidates:
            raise AssertionError(
                f"no call was made{'' if role is None else f' for role {role!r}'}. "
                f"Roles called: {sorted({call.role for call in self._calls}) or 'none'}"
            )
        return candidates[-1]

    def count(self, role: Role | None = None) -> int:
        return len(self._calls if role is None else self.calls_for(role))

    def prompts(self, role: Role | None = None) -> tuple[str, ...]:
        source = self._calls if role is None else list(self.calls_for(role))
        return tuple(call.prompt for call in source)

    # -- internals ---------------------------------------------------------

    def _match(self, request: LLMRequest) -> Script | None:
        for index, script in enumerate(self.scripts):
            if not script.matches(request):
                continue
            if script.times is not None and self._used.get(index, 0) >= script.times:
                continue
            self._used[index] = self._used.get(index, 0) + 1
            return script
        if self.default is not None:
            return Script(respond=self.default)
        return None

    def _unmatched_message(self, request: LLMRequest) -> str:
        """The message a developer reads when a prompt changed shape."""
        offers = (
            ", ".join(
                f"[role={script.role or 'any'} contains={script.contains!r}]"
                for script in self.scripts
            )
            or "none"
        )
        tail = request.prompt_text[-300:]
        return (
            f"FakeLLM has no scripted response for role={request.tags.role!r} "
            f"model={request.model!r}. Scripts tried: {offers}. "
            f"End of the prompt that arrived:\n…{tail}"
        )
