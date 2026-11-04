"""Everything the validator needs to judge one query, loaded once (arch 7.1)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from charie.catalog.browse import Catalog, active_catalog
from charie.config import Settings, get_settings
from charie.connectors.base import Caps, ExecLimits
from charie.connectors.factory import caps_for
from charie.datasources.service import get_data_source

__all__ = [
    "POLICY_TTL_SECONDS",
    "SourcePolicy",
    "invalidate_all",
    "invalidate_source",
    "source_policy",
]

#: How long a loaded context may be reused.
POLICY_TTL_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    """One data source, as the validator sees it."""

    org_id: uuid.UUID
    data_source_id: uuid.UUID
    engine: str
    #: Per-engine truth — dialect, quoting, how a deadline is imposed.
    caps: Caps
    #: The active snapshot, with each column's effective policy already resolved.
    catalog: Catalog
    #: The ceiling every execution runs under.
    limits: ExecLimits

    @property
    def dialect(self) -> str:
        return self.caps.dialect

    def limits_for(self, max_rows: int | None) -> ExecLimits:
        """Bounds for one execution: the caller's wish, clamped to the ceiling."""
        if max_rows is None or max_rows >= self.limits.max_rows:
            return self.limits
        return ExecLimits(max_rows=max(max_rows, 1), timeout_seconds=self.limits.timeout_seconds)


_CACHE: dict[tuple[uuid.UUID, uuid.UUID], tuple[float, SourcePolicy]] = {}


async def source_policy(
    org_id: uuid.UUID, data_source_id: uuid.UUID, *, settings: Settings | None = None
) -> SourcePolicy:
    """Load — or reuse — everything needed to validate against one data source."""
    key = (org_id, data_source_id)
    cached = _CACHE.get(key)
    now = time.monotonic()
    if cached is not None and now - cached[0] < POLICY_TTL_SECONDS:
        return cached[1]

    # Both reads are org-scoped and go through the tenant session.
    resolved = settings if settings is not None else get_settings()
    source = await get_data_source(org_id, data_source_id)
    policy = SourcePolicy(
        org_id=org_id,
        data_source_id=data_source_id,
        engine=source.engine,
        caps=caps_for(source.engine),
        catalog=await active_catalog(org_id, data_source_id),
        limits=ExecLimits(
            max_rows=resolved.dal_max_rows, timeout_seconds=resolved.dal_timeout_seconds
        ),
    )
    _CACHE[key] = (now, policy)
    return policy


def invalidate_source(org_id: uuid.UUID, data_source_id: uuid.UUID) -> None:
    """Forget one source's context — called when a policy or catalog changes."""
    _CACHE.pop((org_id, data_source_id), None)


def invalidate_all() -> None:
    """Empty the cache. For tests, and for a process that has just migrated."""
    _CACHE.clear()
