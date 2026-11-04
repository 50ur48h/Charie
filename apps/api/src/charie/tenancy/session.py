"""The only way feature code reaches the platform database."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from charie.config import Settings, get_settings
from charie.db.engine import build_engine
from charie.tenancy.context import current_context

ORG_SETTING = "app.org_id"

# set_config(name, value, is_local) is the parameterisable form of SET LOCAL.
_SET_ORG = text("SELECT set_config(:name, :value, true)")


def build_app_engine(settings: Settings | None = None) -> AsyncEngine:
    """An engine connected as ``charie_app`` — no superuser, no BYPASSRLS."""
    resolved = settings if settings is not None else get_settings()
    return build_engine(url=resolved.require_app_database_url())


@lru_cache(maxsize=1)
def get_app_engine() -> AsyncEngine:
    return build_app_engine()


@lru_cache(maxsize=1)
def _session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_app_engine(), expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def org_session(org_id: uuid.UUID) -> AsyncGenerator[AsyncSession]:
    """A session scoped to one organization for the life of one transaction."""
    factory = _session_factory()
    async with factory() as session, session.begin():
        await session.execute(_SET_ORG, {"name": ORG_SETTING, "value": str(org_id)})
        yield session


@asynccontextmanager
async def app_session() -> AsyncGenerator[AsyncSession]:
    """The application role, with no organization set."""
    factory = _session_factory()
    async with factory() as session:
        yield session


@asynccontextmanager
async def tenant_session() -> AsyncGenerator[AsyncSession]:
    """A session for the organization of the current request."""
    async with org_session(current_context().org_id) as session:
        yield session


async def current_org_setting(session: AsyncSession) -> str | None:
    """Read back the organization the database believes this session is scoped to."""
    result = await session.execute(
        text("SELECT current_setting(:name, true)"), {"name": ORG_SETTING}
    )
    return result.scalar_one_or_none()
