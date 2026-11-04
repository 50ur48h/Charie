"""Provider-agnostic, metered model calls (architecture Part 4.9, 8.3)."""

from __future__ import annotations

from charie.llm.base import (
    DEFAULT_ROLE_TIERS,
    ROLES,
    TIERS,
    CallLimits,
    Completion,
    LLMError,
    LLMProvider,
    LLMRequest,
    Message,
    ProviderCaps,
    Role,
    Tags,
    Tier,
    Usage,
)
from charie.llm.fake import FakeLLM, NoScriptedResponseError
from charie.llm.registry import ModelChoice, ProviderNotConfiguredError, resolve
from charie.llm.service import complete
from charie.llm.structured import StructuredOutputError

__all__ = [
    "DEFAULT_ROLE_TIERS",
    "ROLES",
    "TIERS",
    "CallLimits",
    "Completion",
    "FakeLLM",
    "LLMError",
    "LLMProvider",
    "LLMRequest",
    "Message",
    "ModelChoice",
    "NoScriptedResponseError",
    "ProviderCaps",
    "ProviderNotConfiguredError",
    "Role",
    "StructuredOutputError",
    "Tags",
    "Tier",
    "Usage",
    "complete",
    "resolve",
]
