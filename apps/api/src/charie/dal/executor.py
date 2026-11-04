"""Running an approved statement, and bounding what comes back (arch 7.1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from charie.connectors.base import Connector
from charie.dal.masking import MaskedFrame, mask_frame, styles_for
from charie.dal.policy import source_policy
from charie.dal.validator import Validated, validate
from charie.datasources import service as datasources

__all__ = ["Execution", "execute"]


@dataclass(frozen=True, slots=True)
class Execution:
    """What one statement did. The object the agent's tool layer will hand on."""

    validated: Validated
    frame: MaskedFrame
    #: The ``query_executions`` row this became.
    execution_id: uuid.UUID | None = None

    @property
    def sql(self) -> str:
        """The canonical statement, as sent. Safe to store: it is our own text."""
        return self.validated.sql

    @property
    def sql_hash(self) -> str:
        return self.validated.query.sql_hash

    @property
    def row_count(self) -> int:
        return self.frame.row_count

    @property
    def truncated(self) -> bool:
        return self.frame.truncated

    @property
    def duration_ms(self) -> int:
        return self.frame.duration_ms

    @property
    def sensitive_accessed(self) -> bool:
        """True when the statement read a column under a mask policy."""
        return self.validated.touches_sensitive


async def execute(
    *,
    org_id: uuid.UUID,
    data_source_id: uuid.UUID,
    sql: str,
    max_rows: int | None = None,
    connector: Connector | None = None,
) -> Execution:
    """Validate, execute, mask. The bounded read, with nothing written down."""
    policy = await source_policy(org_id, data_source_id)
    limits = policy.limits_for(max_rows)

    # Validation first, and the row cap is part of it.
    validated = validate(sql, source=policy, max_rows=limits.max_rows)

    supplied = connector is not None
    if connector is None:
        view = await datasources.get_data_source(org_id, data_source_id)
        connector = await datasources.connector_for_view(view)

    try:
        frame = await connector.execute(validated.query, limits)
    finally:
        if not supplied:
            await connector.aclose()

    return Execution(
        validated=validated,
        frame=mask_frame(frame, validated.projections, styles_for(policy.catalog)),
    )
