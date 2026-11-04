"""Who the current request belongs to."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass


class MissingTenantContextError(RuntimeError):
    """Raised when code asks for tenant-scoped data outside a request context."""

    def __init__(self) -> None:
        super().__init__(
            "No tenant context is set. Feature code must run inside a request "
            "whose organization is known; background and bootstrap work uses "
            "system_session() and is audited separately."
        )


@dataclass(frozen=True, slots=True)
class TenantContext:
    org_id: uuid.UUID
    user_id: uuid.UUID | None = None
    role: str | None = None


_current: ContextVar[TenantContext | None] = ContextVar("charie_tenant_context", default=None)


def current_context() -> TenantContext:
    context = _current.get()
    if context is None:
        raise MissingTenantContextError
    return context


def current_context_or_none() -> TenantContext | None:
    return _current.get()


def set_tenant_context(context: TenantContext) -> Token[TenantContext | None]:
    return _current.set(context)


def reset_tenant_context(token: Token[TenantContext | None]) -> None:
    _current.reset(token)


@contextmanager
def tenant_context(context: TenantContext) -> Generator[TenantContext]:
    """Scope a block of work to one organization."""
    token = set_tenant_context(context)
    try:
        yield context
    finally:
        reset_tenant_context(token)
