"""A way back into an organization whose Admins can no longer sign in (B-017)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from charie.db.models import OrgMembership, OrgRecoveryGrant, User
from charie.orgs.service import ConflictError, audit
from charie.tenancy.session import app_session, org_session

__all__ = [
    "ClaimedRecovery",
    "GrantView",
    "IssuedGrant",
    "arm_grant",
    "claim_recovery",
    "list_grants",
    "revoke_grant",
]

TOKEN_BYTES = 32
ROLE_ADMIN = "admin"

#: A year.
DEFAULT_VALIDITY = timedelta(days=365)

#: Beyond which "arm in advance" stops meaning anything a person can reason about.
MAX_VALIDITY = timedelta(days=730)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedGrant:
    grant_id: uuid.UUID
    label: str
    expires_at: datetime
    #: Shown once. Not recoverable afterwards, by design.
    token: str


@dataclass(frozen=True, slots=True)
class GrantView:
    """One armed grant, without anything that could be redeemed."""

    id: uuid.UUID
    label: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None

    @property
    def state(self) -> str:
        """What an Admin needs to know at a glance."""
        if self.used_at is not None:
            return "used"
        if self.revoked_at is not None:
            return "revoked"
        if self.expires_at <= datetime.now(UTC):
            return "expired"
        return "armed"


@dataclass(frozen=True, slots=True)
class ClaimedRecovery:
    org_id: uuid.UUID
    org_name: str
    #: Whether this created a membership or raised an existing one.
    was_member: bool


async def arm_grant(
    *, org_id: uuid.UUID, actor_user_id: uuid.UUID, label: str, validity: timedelta | None = None
) -> IssuedGrant:
    """Mint a recovery token for this organization, shown once."""
    window = validity or DEFAULT_VALIDITY
    if window > MAX_VALIDITY:
        raise ConflictError(f"A recovery grant can be valid for at most {MAX_VALIDITY.days} days.")
    if window <= timedelta(0):
        raise ConflictError("A recovery grant has to be valid for at least a day.")

    token = secrets.token_urlsafe(TOKEN_BYTES)
    grant_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + window
    cleaned = label.strip() or "Recovery grant"

    async with org_session(org_id) as session:
        session.add(
            OrgRecoveryGrant(
                id=grant_id,
                org_id=org_id,
                token_hash=hash_token(token),
                label=cleaned,
                created_by=actor_user_id,
                expires_at=expires_at,
            )
        )
        # The label and the expiry, never the token or its hash.
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="org.recovery_armed",
            object_type="recovery_grant",
            object_id=str(grant_id),
            details={"label": cleaned, "expires_at": expires_at.isoformat()},
        )

    return IssuedGrant(grant_id=grant_id, label=cleaned, expires_at=expires_at, token=token)


async def list_grants(*, org_id: uuid.UUID) -> list[GrantView]:
    """Every grant this organization has ever armed, newest first."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(OrgRecoveryGrant).order_by(OrgRecoveryGrant.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [
            GrantView(
                id=row.id,
                label=row.label,
                created_at=row.created_at,
                expires_at=row.expires_at,
                used_at=row.used_at,
                revoked_at=row.revoked_at,
            )
            for row in rows
        ]


async def revoke_grant(
    *, org_id: uuid.UUID, actor_user_id: uuid.UUID, grant_id: uuid.UUID
) -> GrantView:
    """Kill a grant whose token may have got out."""
    async with org_session(org_id) as session:
        row = (
            (await session.execute(select(OrgRecoveryGrant).where(OrgRecoveryGrant.id == grant_id)))
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise ConflictError("No such recovery grant.")
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="org.recovery_revoked",
            object_type="recovery_grant",
            object_id=str(grant_id),
            details={"label": row.label},
        )
        return GrantView(
            id=row.id,
            label=row.label,
            created_at=row.created_at,
            expires_at=row.expires_at,
            used_at=row.used_at,
            revoked_at=row.revoked_at,
        )


async def claim_recovery(*, user: User, token: str) -> ClaimedRecovery:
    """Redeem a grant and become an Admin of its organization."""
    invalid = ConflictError("That recovery grant is not valid.")

    # Same shape as `accept_invitation`: the token is all that is known.
    async with app_session() as session:
        found = (
            await session.execute(
                text(
                    "SELECT id, org_id, org_name, expires_at, used_at, revoked_at "
                    "FROM auth_recovery_grant_by_token(CAST(:token_hash AS varchar))"
                ),
                {"token_hash": hash_token(token)},
            )
        ).one_or_none()

    if found is None or found.used_at is not None or found.revoked_at is not None:
        raise invalid
    if found.expires_at <= datetime.now(UTC):
        raise invalid

    grant_id = found.id
    org_name = found.org_name

    org_id = found.org_id

    async with org_session(org_id) as session:
        # Re-read inside the org session, and mark it used there.
        held = (
            (
                await session.execute(
                    select(OrgRecoveryGrant).where(
                        OrgRecoveryGrant.id == grant_id, OrgRecoveryGrant.used_at.is_(None)
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if held is None:
            raise invalid
        held.used_at = datetime.now(UTC)
        held.used_by = user.id

        membership = (
            (
                await session.execute(
                    select(OrgMembership).where(
                        OrgMembership.org_id == org_id, OrgMembership.user_id == user.id
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        was_member = membership is not None
        previous = membership.role if membership is not None else None
        if membership is None:
            session.add(OrgMembership(org_id=org_id, user_id=user.id, role=ROLE_ADMIN))
        else:
            membership.role = ROLE_ADMIN

        audit(
            session,
            org_id=org_id,
            actor_user_id=user.id,
            action="org.recovery_claimed",
            object_type="recovery_grant",
            object_id=str(grant_id),
            details={"label": held.label, "was_member": was_member, "previous_role": previous},
        )

    return ClaimedRecovery(org_id=org_id, org_name=org_name, was_member=was_member)
