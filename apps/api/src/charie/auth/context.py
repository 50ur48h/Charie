"""Turning a principal into "who, in which organization, with what role"."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text

from charie.auth.principal import Principal
from charie.db.models import User
from charie.tenancy.session import app_session


class AuthorizationError(Exception):
    """The caller is known but may not do this."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Everything authorization needs, resolved once per request."""

    principal: Principal
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str


async def resolve_user_id(principal: Principal) -> uuid.UUID | None:
    """The local user row for this token's subject, if we have ever seen them."""
    # `users` is not tenant-scoped and carries no RLS policy.
    async with app_session() as session:
        result = await session.execute(
            select(User.id).where(User.external_subject == principal.subject)
        )
        return result.scalars().one_or_none()


async def resolve_context(principal: Principal, org_id: uuid.UUID) -> RequestContext:
    """Resolve a principal's membership of one organization."""
    user_id = await resolve_user_id(principal)
    if user_id is None:
        raise AuthorizationError(
            "unknown_user", "No account exists for this identity in this deployment"
        )

    # `org_memberships` is a tenant table and this read happens before the tenant is known.
    async with app_session() as session:
        result = await session.execute(
            text("SELECT auth_membership_role(CAST(:user_id AS uuid), CAST(:org_id AS uuid))"),
            {"user_id": user_id, "org_id": org_id},
        )
        role = result.scalar_one_or_none()

    if role is None:
        raise AuthorizationError(
            "not_a_member", "This account is not a member of the requested organization"
        )

    return RequestContext(principal=principal, user_id=user_id, org_id=org_id, role=role)
