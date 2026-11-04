"""Organizations, membership and the audit trail they leave."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from charie.auth.principal import Principal
from charie.db.models import AuditLog, DataSource, Organization, OrgMembership, User
from charie.tenancy.session import app_session, org_session

ROLE_ADMIN = "admin"


class ConflictError(Exception):
    """A request that is well-formed but cannot be applied to the current state."""


class NotFoundError(Exception):
    """Named a row this organization cannot see — which reads the same as absent."""


@dataclass(frozen=True, slots=True)
class Membership:
    org_id: uuid.UUID
    org_name: str
    role: str


def audit(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    object_type: str | None = None,
    object_id: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Stage an audit row on an already org-scoped session."""
    session.add(
        AuditLog(
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details or {},
            sensitive=False,
        )
    )


async def ensure_user(principal: Principal) -> User:
    """Find or create the local user row for a validated principal."""
    # `users` is not tenant-scoped and has no RLS policy.
    async with app_session() as session:
        existing = (
            (await session.execute(select(User).where(User.external_subject == principal.subject)))
            .scalars()
            .one_or_none()
        )

        if existing is not None:
            # Filling a blank, never overwriting: the token is authoritative about who this is.
            filled = False
            if existing.email is None and principal.email:
                existing.email, filled = principal.email, True
            if existing.name is None and principal.name:
                existing.name, filled = principal.name, True
            if filled:
                await session.commit()
                await session.refresh(existing)
            return existing

        user = User(
            external_subject=principal.subject,
            email=principal.email,
            name=principal.name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def memberships_for(user_id: uuid.UUID) -> list[Membership]:
    """Every organization this user belongs to."""
    # Spans every organization by definition.
    async with app_session() as session:
        rows = await session.execute(
            text(
                "SELECT org_id, org_name, member_role "
                "FROM auth_memberships_for_user(CAST(:user_id AS uuid))"
            ),
            {"user_id": user_id},
        )
        return [Membership(org_id=o, org_name=n, role=r) for o, n, r in rows.all()]


async def create_organization(user: User, name: str) -> Membership:
    """Create an organization; the creator becomes its Admin."""
    org_id = uuid.uuid4()  # chosen here, not by the database — see the module docstring

    async with org_session(org_id) as session:
        session.add(Organization(id=org_id, name=name))
        await session.flush()
        session.add(OrgMembership(org_id=org_id, user_id=user.id, role=ROLE_ADMIN))
        audit(
            session,
            org_id=org_id,
            actor_user_id=user.id,
            action="org.created",
            object_type="organization",
            object_id=str(org_id),
            details={"name": name},
        )

    return Membership(org_id=org_id, org_name=name, role=ROLE_ADMIN)


@dataclass(frozen=True, slots=True)
class Member:
    user_id: uuid.UUID
    #: None when the identity provider never sent an email claim (B-009).
    email: str | None
    name: str | None
    role: str


async def list_members(org_id: uuid.UUID) -> list[Member]:
    async with org_session(org_id) as session:
        rows = await session.execute(
            select(OrgMembership.user_id, User.email, User.name, OrgMembership.role)
            .join(User, User.id == OrgMembership.user_id)
            .where(OrgMembership.org_id == org_id)
            .order_by(User.email)
        )
        return [Member(user_id=u, email=e, name=n, role=r) for u, e, n, r in rows.all()]


async def _count_admins(session: AsyncSession, org_id: uuid.UUID) -> int:
    rows = await session.execute(
        select(OrgMembership.user_id).where(
            OrgMembership.org_id == org_id, OrgMembership.role == ROLE_ADMIN
        )
    )
    return len(rows.scalars().all())


async def change_role(
    *, org_id: uuid.UUID, actor_user_id: uuid.UUID, target_user_id: uuid.UUID, role: str
) -> Member:
    """Change a member's role, refusing to remove the last Admin."""
    async with org_session(org_id) as session:
        membership = (
            (
                await session.execute(
                    select(OrgMembership).where(
                        OrgMembership.org_id == org_id, OrgMembership.user_id == target_user_id
                    )
                )
            )
            .scalars()
            .one_or_none()
        )

        if membership is None:
            raise ConflictError("That user is not a member of this organization")

        demoting_an_admin = membership.role == ROLE_ADMIN and role != ROLE_ADMIN
        if demoting_an_admin and await _count_admins(session, org_id) <= 1:
            raise ConflictError(
                "This is the only Admin. Promote someone else before changing this role."
            )

        previous, membership.role = membership.role, role
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="member.role_changed",
            object_type="user",
            object_id=str(target_user_id),
            details={"from": previous, "to": role},
        )

        user = (
            (await session.execute(select(User).where(User.id == target_user_id))).scalars().one()
        )
        return Member(user_id=user.id, email=user.email, name=user.name, role=role)


async def remove_member(
    *, org_id: uuid.UUID, actor_user_id: uuid.UUID, target_user_id: uuid.UUID
) -> None:
    async with org_session(org_id) as session:
        membership = (
            (
                await session.execute(
                    select(OrgMembership).where(
                        OrgMembership.org_id == org_id, OrgMembership.user_id == target_user_id
                    )
                )
            )
            .scalars()
            .one_or_none()
        )

        if membership is None:
            raise ConflictError("That user is not a member of this organization")

        if membership.role == ROLE_ADMIN and await _count_admins(session, org_id) <= 1:
            raise ConflictError("This is the only Admin and cannot be removed.")

        await session.delete(membership)
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="member.removed",
            object_type="user",
            object_id=str(target_user_id),
        )


@dataclass(frozen=True, slots=True)
class ActiveDataSource:
    """Which database this organization asks questions of, and its name."""

    data_source_id: uuid.UUID | None
    data_source_name: str | None


async def _active_data_source(session: AsyncSession, org: Organization) -> ActiveDataSource:
    """Read the pointer and resolve its name on an already org-scoped session."""
    if org.active_data_source_id is None:
        return ActiveDataSource(data_source_id=None, data_source_name=None)
    name = (
        await session.execute(
            select(DataSource.name).where(DataSource.id == org.active_data_source_id)
        )
    ).scalar_one_or_none()
    # A source deleted between the two statements would land here.
    if name is None:
        return ActiveDataSource(data_source_id=None, data_source_name=None)
    return ActiveDataSource(data_source_id=org.active_data_source_id, data_source_name=name)


async def active_data_source(org_id: uuid.UUID) -> ActiveDataSource:
    """The organization's chosen database, readable by any member."""
    async with org_session(org_id) as session:
        org = (
            (await session.execute(select(Organization).where(Organization.id == org_id)))
            .scalars()
            .one()
        )
        return await _active_data_source(session, org)


#: The key in ``organizations.settings`` holding whether an answer shows what it cost.
SHOW_RUN_COST = "show_run_cost"


def show_run_cost_of(org: Organization) -> bool:
    """Whether this organization's answers carry cost and token counts."""
    return (org.settings or {}).get(SHOW_RUN_COST) is not False


async def show_run_cost(org_id: uuid.UUID) -> bool:
    """The switch, readable by any member — every member is subject to it."""
    async with org_session(org_id) as session:
        org = (
            (await session.execute(select(Organization).where(Organization.id == org_id)))
            .scalars()
            .one()
        )
        return show_run_cost_of(org)


async def set_show_run_cost(*, org_id: uuid.UUID, actor_user_id: uuid.UUID, visible: bool) -> bool:
    """Turn spend on or off for the whole organization."""
    async with org_session(org_id) as session:
        org = (
            (await session.execute(select(Organization).where(Organization.id == org_id)))
            .scalars()
            .one()
        )
        previous = show_run_cost_of(org)
        # Reassigned rather than mutated: SQLAlchemy does not track a mutation inside a JSONB dict.
        org.settings = {**(org.settings or {}), SHOW_RUN_COST: visible}
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="org.show_run_cost_changed",
            object_type="organization",
            object_id=str(org_id),
            details={"from": previous, "to": visible},
        )
        await session.flush()
        return visible


async def set_active_data_source(
    *, org_id: uuid.UUID, actor_user_id: uuid.UUID, data_source_id: uuid.UUID | None
) -> ActiveDataSource:
    """Choose the database this organization asks questions of."""
    async with org_session(org_id) as session:
        org = (
            (await session.execute(select(Organization).where(Organization.id == org_id)))
            .scalars()
            .one()
        )

        if data_source_id is not None:
            owned = (
                (await session.execute(select(DataSource).where(DataSource.id == data_source_id)))
                .scalars()
                .one_or_none()
            )
            if owned is None:
                raise NotFoundError("No such data source")

        previous = org.active_data_source_id
        org.active_data_source_id = data_source_id
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="org.active_data_source_changed",
            object_type="data_source",
            object_id=str(data_source_id) if data_source_id is not None else None,
            details={
                "from": str(previous) if previous is not None else None,
                "to": str(data_source_id) if data_source_id is not None else None,
            },
        )
        await session.flush()
        return await _active_data_source(session, org)
