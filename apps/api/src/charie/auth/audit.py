"""Recording access-control decisions (DECISIONS D-008)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from charie.auth.context import RequestContext
from charie.auth.principal import Principal
from charie.db.models import AuditLog
from charie.db.security_events import record_security_event
from charie.tenancy.session import org_session

logger = logging.getLogger(__name__)

AUTH_DENIED = "auth.denied"


def log_unauthenticated(*, reason: str, route: str | None, method: str | None) -> None:
    """A 401. Application log only, and deliberately so."""
    # In the message, not in `extra`: the default formatter drops extras.
    logger.warning(
        "rejected an unauthenticated request: reason=%s %s %s", reason, method or "-", route or "-"
    )


async def record_denial(
    *,
    context: RequestContext | None,
    principal: Principal | None,
    reason: str,
    attempted_org_id: uuid.UUID | None,
    route: str | None,
    method: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    """A 403, recorded wherever it can honestly be attributed."""
    if context is not None:
        await _record_org_denial(
            context=context, reason=reason, route=route, method=method, details=details
        )
        return

    await record_security_event(
        action=AUTH_DENIED,
        reason=reason,
        actor_subject=principal.subject if principal else None,
        attempted_org_id=attempted_org_id,
        route=route,
        method=method,
        details=details,
    )


async def _record_org_denial(
    *,
    context: RequestContext,
    reason: str,
    route: str | None,
    method: str | None,
    details: dict[str, Any] | None,
) -> None:
    payload: dict[str, object] = {"reason": reason, "role": context.role, **(details or {})}
    try:
        async with org_session(context.org_id) as session:
            session.add(
                AuditLog(
                    org_id=context.org_id,
                    actor_user_id=context.user_id,
                    action=AUTH_DENIED,
                    object_type="route",
                    object_id=f"{method} {route}" if route else None,
                    details=payload,
                    sensitive=False,
                )
            )
    except Exception:
        # A failure to audit must not turn a 403 into a 500: the caller is being refused either way.
        logger.exception("could not write an audit row for a denial")
        await record_security_event(
            action=AUTH_DENIED,
            reason=reason,
            outcome="error",
            actor_subject=context.principal.subject,
            actor_user_id=context.user_id,
            attempted_org_id=context.org_id,
            route=route,
            method=method,
            details={"audit_write_failed": True, **payload},
        )
