"""The data access layer's front door (architecture Part 7.1)."""

from __future__ import annotations

import uuid
from dataclasses import replace

from charie.connectors.base import Connector, ConnectorError
from charie.dal import audit_hook
from charie.dal.artifacts import ArtifactStore, artifact_store
from charie.dal.errors import PolicyViolation
from charie.dal.executor import Execution, execute

__all__ = ["run"]


async def run(
    *,
    org_id: uuid.UUID,
    data_source_id: uuid.UUID,
    sql: str,
    actor_user_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    max_rows: int | None = None,
    store: ArtifactStore | None = None,
    connector: Connector | None = None,
) -> Execution:
    """Validate, execute, mask, record."""
    resolved_store = store if store is not None else artifact_store()

    try:
        execution = await execute(
            org_id=org_id,
            data_source_id=data_source_id,
            sql=sql,
            max_rows=max_rows,
            # Supplied by the run's lease where there is one (B-176).
            connector=connector,
        )
    except PolicyViolation as violation:
        await audit_hook.record_refusal(
            org_id=org_id,
            data_source_id=data_source_id,
            actor_user_id=actor_user_id,
            sql=sql,
            violation=violation,
            run_id=run_id,
        )
        raise
    except ConnectorError as error:
        await audit_hook.record_failure(
            org_id=org_id,
            data_source_id=data_source_id,
            actor_user_id=actor_user_id,
            sql=sql,
            sql_hash=audit_hook.hash_sql(sql),
            error=str(error),
            run_id=run_id,
        )
        raise

    recorded = await audit_hook.record_success(
        org_id=org_id,
        data_source_id=data_source_id,
        actor_user_id=actor_user_id,
        execution=execution,
        store=resolved_store,
        run_id=run_id,
    )
    # The id goes back to the caller because a citation must name a row somebody can look up.
    return replace(execution, execution_id=recorded.execution_id)
