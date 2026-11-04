"""What actually runs a queued run (architecture 0.2.4 and Part 8.2)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import text

from charie.agent.runner import execute_run
from charie.config import Settings
from charie.datasources import service as datasources
from charie.llm import registry
from charie.orgs import service as orgs_service
from charie.runs import service as runs
from charie.tenancy.session import app_session

__all__ = [
    "AmbiguousDataSourceError",
    "in_flight",
    "resolve_data_source",
    "schedule_run",
    "sweep_orphaned_runs",
]

logger = logging.getLogger(__name__)

#: Concurrent runs per organization (architecture 8.4).
MAX_CONCURRENT_RUNS_PER_ORG = 2

#: What a run is told when the service restarted underneath it.
INTERRUPTED_REASON = (
    "The service restarted while this run was in progress, so it was stopped "
    "part-way. Nothing was wrong with the question — ask it again to retry."
)

#: Statuses a run cannot still be in after a restart.
ORPHANABLE = ("queued", "running", "validating")

_semaphores: dict[uuid.UUID, asyncio.Semaphore] = {}
#: Strong references to in-flight tasks. asyncio keeps only a weak one.
_running: set[asyncio.Task[None]] = set()


class AmbiguousDataSourceError(Exception):
    """There is no single obvious data source to answer against."""

    def __init__(self, message: str, *, candidates: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.candidates = tuple(candidates)


async def resolve_data_source(org_id: uuid.UUID) -> uuid.UUID:
    """The one data source to answer from, or a refusal that says why not."""
    chosen = await orgs_service.active_data_source(org_id)
    if chosen.data_source_id is not None:
        return chosen.data_source_id

    sources = await datasources.list_data_sources(org_id)
    if not sources:
        raise AmbiguousDataSourceError(
            "No data source is registered for this organization, so there is "
            "nothing to query. An Admin can add one on the data sources screen."
        )
    if len(sources) > 1:
        names = [source.name for source in sources]
        raise AmbiguousDataSourceError(
            "This organization has more than one data source and this conversation "
            f"is not tied to one of them: {', '.join(names)}. Start a conversation "
            "that names the database you mean.",
            candidates=names,
        )
    return sources[0].id


async def schedule_run(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    role: str = "reader",
    data_source_id: uuid.UUID | None = None,
    settings: Settings | None = None,
    model: str | None = None,
) -> asyncio.Task[None]:
    """Start a queued run in the background and return immediately."""
    task = asyncio.create_task(
        _guarded(
            org_id=org_id,
            run_id=run_id,
            actor_user_id=actor_user_id,
            role=role,
            data_source_id=data_source_id,
            settings=settings,
            model=model,
        )
    )
    _running.add(task)
    task.add_done_callback(_running.discard)
    return task


def in_flight() -> frozenset[asyncio.Task[None]]:
    """The runs this process is currently executing."""
    return frozenset(_running)


async def _guarded(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    role: str,
    data_source_id: uuid.UUID | None,
    settings: Settings | None,
    model: str | None = None,
) -> None:
    """Resolve the source, wait for a slot, run — and never raise into the loop."""
    try:
        resolved = data_source_id or await resolve_data_source(org_id)
    except AmbiguousDataSourceError as choice:
        await _refuse(org_id=org_id, run_id=run_id, reason=str(choice))
        return
    except Exception:
        logger.exception("could not resolve a data source for run %s", run_id)
        await _refuse(
            org_id=org_id,
            run_id=run_id,
            reason="I could not work out which database to query.",
        )
        return

    async with _semaphore_for(org_id):
        try:
            with registry.use_model(model):
                await execute_run(
                    org_id=org_id,
                    run_id=run_id,
                    data_source_id=resolved,
                    actor_user_id=actor_user_id,
                    role=role,
                    settings=settings,
                )
        except Exception:
            # `execute_run` already ends the run on every path it knows about.
            logger.exception("run %s ended abnormally", run_id)


async def _refuse(*, org_id: uuid.UUID, run_id: uuid.UUID, reason: str) -> None:
    """End a run that never got as far as the agent."""
    await runs.transition(org_id=org_id, run_id=run_id, status="running")
    await runs.record_answer(org_id=org_id, run_id=run_id, content=reason)
    await runs.transition(
        org_id=org_id,
        run_id=run_id,
        status="completed",
        # The run never reached the agent.
        state="refused",
        unanswered="this question",
        totals={"llm_calls": 0, "queries": 0, "state": "refused"},
    )


def _semaphore_for(org_id: uuid.UUID) -> asyncio.Semaphore:
    semaphore = _semaphores.get(org_id)
    if semaphore is None:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS_PER_ORG)
        _semaphores[org_id] = semaphore
    return semaphore


async def sweep_orphaned_runs() -> int:
    """Mark runs that a restart stopped, and return how many."""
    # Spans every organization by definition.
    async with app_session() as session:
        rows = (await session.execute(text("SELECT run_id, org_id FROM ops_orphaned_runs()"))).all()

    swept = 0
    for run_id, org_id in rows:
        try:
            await runs.transition(
                org_id=org_id,
                run_id=run_id,
                status="interrupted",
                failure_reason=INTERRUPTED_REASON,
                totals={"interrupted_by": "restart"},
            )
        except Exception:
            # One unreconcilable run must not stop the rest being reconciled.
            logger.exception("could not mark run %s as interrupted", run_id)
            continue
        swept += 1

    if swept:
        logger.warning("marked %d run(s) interrupted after a restart", swept)
    return swept
