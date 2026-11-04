"""Which model does which job, and who supplies it (architecture Part 4.9, 8.3)."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass

from charie.config import Settings, get_settings
from charie.llm.base import (
    DEFAULT_ROLE_TIERS,
    ROLES,
    TIERS,
    LLMError,
    LLMProvider,
    Role,
    Tier,
)

__all__ = [
    "STUB_PROVIDERS",
    "ModelChoice",
    "ProviderNotConfiguredError",
    "aclose_providers",
    "clear_provider_cache",
    "default_model",
    "get_provider",
    "register_provider",
    "resolve",
    "selectable_models",
    "tier_for",
    "unresolvable_roles",
    "use_model",
]


class ProviderNotConfiguredError(LLMError):
    """Configuration cannot answer "which model, from whom"."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """One resolved answer to "what should serve this role"."""

    role: Role
    tier: Tier
    provider: str
    model: str


def _meta() -> LLMProvider:
    # The same Responses client with Meta's endpoint and key (D-069).
    from charie.llm.meta import MetaProvider

    return MetaProvider()


#: Providers this build ships.
def _scripted() -> LLMProvider:
    from charie.llm.scripted import ScriptedProvider

    return ScriptedProvider()


_BUILTIN_FACTORIES: dict[str, Callable[[], LLMProvider]] = {
    "meta": _meta,
    # A stub, shipped deliberately (WP11.2b).
    "scripted": _scripted,
}

#: The built-in providers that answer without a model behind them.
STUB_PROVIDERS: frozenset[str] = frozenset({"scripted"})

#: Registered at runtime — by tests.
_OVERRIDES: dict[str, Callable[[], LLMProvider]] = {}

#: One instance per provider name.
_INSTANCES: dict[str, LLMProvider] = {}


def register_provider(name: str, factory: Callable[[], LLMProvider]) -> None:
    """Make ``name`` resolvable, replacing any earlier registration."""
    _OVERRIDES[name] = factory
    _INSTANCES.pop(name, None)


def clear_provider_cache() -> None:
    """Drop cached instances and every runtime registration."""
    _OVERRIDES.clear()
    _INSTANCES.clear()


async def aclose_providers() -> None:
    """Close every built provider and forget it."""
    for provider in list(_INSTANCES.values()):
        with suppress(Exception):
            await provider.aclose()
    _INSTANCES.clear()


def get_provider(name: str, settings: Settings | None = None) -> LLMProvider:
    """The provider registered under ``name``, built once and kept."""
    cached = _INSTANCES.get(name)
    if cached is not None:
        return cached

    factory = _OVERRIDES.get(name) or _BUILTIN_FACTORIES.get(name)
    if factory is None:
        known = sorted(set(_OVERRIDES) | set(_BUILTIN_FACTORIES))
        raise ProviderNotConfiguredError(
            f"no LLM provider named {name!r} is registered. "
            f"Registered: {known or 'none'}. Check LLM_PROVIDERS."
        )

    provider = factory()
    resolved = settings if settings is not None else get_settings()
    if provider.capabilities().is_stub and resolved.is_production:
        raise ProviderNotConfiguredError(
            f"{name!r} answers without a model behind it and is not permitted in a "
            "production build or environment: it would fabricate answers in a "
            "product whose whole claim is that answers are evidenced."
        )

    _INSTANCES[name] = provider
    return provider


def tier_for(role: Role, settings: Settings | None = None) -> Tier:
    """How much model this role is worth, after configuration has its say."""
    resolved = settings if settings is not None else get_settings()
    override = resolved.llm_role_map.get(role)
    if override is None:
        return DEFAULT_ROLE_TIERS[role]
    if override not in TIERS:
        raise ProviderNotConfiguredError(
            f"LLM_ROLE_MAP maps role {role!r} to {override!r}, which is not a tier. "
            f"Tiers are {list(TIERS)}."
        )
    return override


#: The model a person picked for the run in progress; None means the configured chain.
_chosen_model: ContextVar[str | None] = ContextVar("charie_chosen_model", default=None)


@contextmanager
def use_model(model: str | None) -> Generator[None]:
    """Serve every role in this context from ``model``, on the primary provider."""
    token = _chosen_model.set(model)
    try:
        yield
    finally:
        _chosen_model.reset(token)


def default_model(settings: Settings | None = None) -> str | None:
    """The model a question gets when nobody picks one: the primary provider's strongest."""
    resolved = settings if settings is not None else get_settings()
    if not resolved.llm_providers:
        return None
    models = resolved.llm_models.get(resolved.llm_providers[0]) or {}
    return models.get("strong") or models.get("mid") or models.get("small")


def selectable_models(settings: Settings | None = None) -> tuple[str, ...]:
    """The models a person may pick, default first."""
    resolved = settings if settings is not None else get_settings()
    first = default_model(resolved)
    offered = list(resolved.llm_selectable_models)
    if not offered and resolved.llm_providers:
        offered = list((resolved.llm_models.get(resolved.llm_providers[0]) or {}).values())
    ordered = ([first] if first else []) + [model for model in offered if model != first]
    return tuple(dict.fromkeys(ordered))


def resolve(role: Role, settings: Settings | None = None) -> tuple[ModelChoice, ...]:
    """The ordered chain of models that may serve ``role``."""
    resolved = settings if settings is not None else get_settings()
    tier = tier_for(role, resolved)

    chosen = _chosen_model.get()
    if chosen is not None and resolved.llm_providers:
        return (
            ModelChoice(role=role, tier=tier, provider=resolved.llm_providers[0], model=chosen),
        )

    if not resolved.llm_providers:
        raise ProviderNotConfiguredError(
            "LLM_PROVIDERS is empty, so no model can serve any role. Set it to an "
            "ordered, comma-separated list — the first is primary, the rest are "
            "fallbacks."
        )

    chain: list[ModelChoice] = []
    for provider in resolved.llm_providers:
        models = resolved.llm_models.get(provider)
        if not models:
            raise ProviderNotConfiguredError(
                f"LLM_MODELS names no models for provider {provider!r}. It must map "
                f"each configured provider to a model per tier: {list(TIERS)}."
            )
        model = models.get(tier)
        if not model:
            raise ProviderNotConfiguredError(
                f"LLM_MODELS has no {tier!r} model for provider {provider!r}, which "
                f"role {role!r} needs. Model ids are deployment configuration; this "
                "build ships none, deliberately, so that a stale default cannot "
                "bill for the wrong tier."
            )
        chain.append(ModelChoice(role=role, tier=tier, provider=provider, model=model))
    return tuple(chain)


def unresolvable_roles(settings: Settings | None = None) -> list[str]:
    """Roles this configuration cannot serve, as ``role -> why`` sentences."""
    resolved = settings if settings is not None else get_settings()
    problems: list[str] = []
    for role in ROLES:
        # `embed` is not resolved here and asking would invent a failure.
        if tier_for(role, resolved) == "embed":
            continue
        try:
            resolve(role, resolved)
        except ProviderNotConfiguredError as error:
            problems.append(f"{role}: {error}")
    return problems
