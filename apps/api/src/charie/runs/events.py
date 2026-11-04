"""The one door every trace event goes through (architecture Part 10.3)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from charie.db.models import AgentEvent, AgentRun
from charie.tenancy.session import org_session

__all__ = [
    "EventType",
    "EventWriter",
    "RecordedEvent",
    "UnknownRunError",
    "read_events",
    "write_event",
]

#: Architecture 10.3's vocabulary, as a type.
EventType = Literal[
    "run_started",
    "intent_classified",
    "context_selected",
    "capability_checked",
    "plan_created",
    "step_started",
    "tool_called",
    # The result of a `tool_called` for `search_knowledge`.
    "knowledge_consulted",
    # One live model call: which model, for which role, how long, how many tokens.
    "model_called",
    "sql_validated",
    "sql_rejected",
    "query_executed",
    "result_summarized",
    "finding_added",
    "hypothesis_updated",
    "reflection",
    "critic_verdict",
    "budget_warning",
    "budget_exhausted",
    "answer_composed",
    "run_finished",
    "error",
]

EVENT_TYPES: tuple[str, ...] = get_args(EventType)


class UnknownRunError(Exception):
    """No run with that id in this organization."""


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """One written event, as a reader of the trace sees it."""

    seq: int
    type: str
    payload: dict[str, object]
    ts: datetime


def _payload(payload: Mapping[str, object] | None) -> dict[str, object]:
    """Reject anything that will not survive the trip to JSONB, here and loudly."""
    if payload is None:
        return {}
    materialised = dict(payload)
    try:
        json.dumps(materialised)
    except (TypeError, ValueError) as error:
        raise TypeError(f"Event payload is not JSON-serialisable: {error}") from error
    return materialised


async def write_event(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    event_type: EventType,
    payload: Mapping[str, object] | None = None,
) -> RecordedEvent:
    """Append one event on an already org-scoped session."""
    locked = (
        await session.execute(select(AgentRun.id).where(AgentRun.id == run_id).with_for_update())
    ).scalar_one_or_none()
    if locked is None:
        raise UnknownRunError(f"No run {run_id} in this organization")

    # MAX + 1 rather than a sequence.
    highest = (
        await session.execute(
            select(func.coalesce(func.max(AgentEvent.seq), 0)).where(AgentEvent.run_id == run_id)
        )
    ).scalar_one()

    row = AgentEvent(
        org_id=org_id,
        run_id=run_id,
        seq=highest + 1,
        type=event_type,
        payload=_payload(payload),
    )
    session.add(row)
    await session.flush()
    return RecordedEvent(seq=row.seq, type=row.type, payload=row.payload, ts=row.ts)


class EventWriter:
    """A trace writer bound to one run."""

    __slots__ = ("_org_id", "_run_id")

    def __init__(self, *, org_id: uuid.UUID, run_id: uuid.UUID) -> None:
        self._org_id = org_id
        self._run_id = run_id

    @property
    def run_id(self) -> uuid.UUID:
        return self._run_id

    async def emit(
        self, event_type: EventType, payload: Mapping[str, object] | None = None
    ) -> RecordedEvent:
        async with org_session(self._org_id) as session:
            return await write_event(
                session,
                org_id=self._org_id,
                run_id=self._run_id,
                event_type=event_type,
                payload=payload,
            )


async def read_events(
    *, org_id: uuid.UUID, run_id: uuid.UUID, after: int = 0, limit: int = 500
) -> list[RecordedEvent]:
    """This run's events after ``seq``, oldest first — the poll and the replay."""
    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(AgentEvent)
                    .where(AgentEvent.run_id == run_id, AgentEvent.seq > after)
                    .order_by(AgentEvent.seq)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [
            RecordedEvent(seq=row.seq, type=row.type, payload=row.payload, ts=row.ts)
            for row in rows
        ]
