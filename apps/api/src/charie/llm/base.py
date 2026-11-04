"""What every LLM provider is, and what a call to one looks like."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

__all__ = [
    "DEFAULT_ROLE_TIERS",
    "ROLES",
    "TIERS",
    "CallLimits",
    "Completion",
    "LLMError",
    "LLMProvider",
    "LLMRequest",
    "Message",
    "ProviderCaps",
    "Role",
    "Tags",
    "Tier",
    "Usage",
    "estimate_tokens",
]

#: The roles from architecture 4.9's ``MODEL_ROLES``.
Role = Literal["intake", "observe", "plan", "sql", "critic", "compose", "embed"]

#: How much model a job is worth.
Tier = Literal["small", "mid", "strong", "embed"]

ROLES: tuple[Role, ...] = ("intake", "observe", "plan", "sql", "critic", "compose", "embed")
TIERS: tuple[Tier, ...] = ("small", "mid", "strong", "embed")

#: Architecture 4.9's table, verbatim.
DEFAULT_ROLE_TIERS: dict[Role, Tier] = {
    "intake": "small",
    "observe": "small",
    "plan": "strong",
    "sql": "strong",
    "critic": "small",
    "compose": "mid",
    # The one entry that is not on 4.9's ladder, and says so by mapping to a tier of its own.
    "embed": "embed",
}


class LLMError(Exception):
    """A failure talking to a model provider, already sanitized."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of the conversation sent to a model."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class CallLimits:
    """What one call may cost, in the small."""

    max_output_tokens: int = 1024
    #: Zero by default. Every role in this product is doing analysis, not prose generation.
    temperature: float = 0.0
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class Tags:
    """Who this call belongs to (architecture 4.9's ``tags{org,run,role}``)."""

    org_id: uuid.UUID
    role: Role
    run_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    """Tokens in and out, as the provider reported them."""

    input_tokens: int = 0
    output_tokens: int = 0
    #: How many of ``input_tokens`` came from the provider's prompt cache.
    cached_input_tokens: int | None = None
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ProviderCaps:
    """Per-provider truth, stated rather than inferred."""

    name: str
    #: Whether the API can be made to return JSON matching a schema.
    supports_response_schema: bool
    #: Some protocols take the system prompt as a separate top-level parameter.
    supports_system_message: bool = True
    max_output_tokens: int = 4096
    #: True for anything that answers without a model behind it.
    is_stub: bool = False


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """One call, fully specified."""

    model: str
    messages: Sequence[Message]
    tags: Tags
    #: A pydantic model the reply must satisfy, or None for free text.
    schema: type[BaseModel] | None = None
    limits: CallLimits = field(default_factory=CallLimits)

    def text_of(self, role: Literal["system", "user", "assistant"]) -> str:
        """Every message of one role, joined. Used for matching and assertions."""
        return "\n".join(message.content for message in self.messages if message.role == role)

    @property
    def prompt_text(self) -> str:
        """The whole conversation as one string."""
        return "\n".join(f"{message.role}: {message.content}" for message in self.messages)


@dataclass(frozen=True, slots=True)
class Completion:
    """What came back, plus what it cost."""

    text: str
    model: str
    provider: str
    usage: Usage
    #: Wall time for this one call. Providers may leave it at zero.
    latency_ms: int
    #: The provider's own word for why generation stopped.
    finish_reason: str = "stop"
    parsed: BaseModel | None = None
    repaired: bool = False

    def parsed_as[ModelT: BaseModel](self, schema: type[ModelT]) -> ModelT:
        """The parsed object, typed — or a failure that says what arrived instead."""
        if not isinstance(self.parsed, schema):
            raise LLMError(
                f"this completion carries no {schema.__name__}: "
                f"parsed is {type(self.parsed).__name__}. Pass schema= to the call "
                "that produced it."
            )
        return self.parsed


@runtime_checkable
class LLMProvider(Protocol):
    """One model API, spoken to in one shape."""

    def capabilities(self) -> ProviderCaps: ...

    async def complete(self, request: LLMRequest) -> Completion:
        """Raises ``LLMError`` and nothing else."""
        ...

    async def aclose(self) -> None:
        """Release the HTTP client. Every caller owes a provider this."""
        ...


def estimate_tokens(text: str) -> int:
    """A rough token count for providers that do not report one."""
    return max(1, len(text) // 4) if text else 0
