"""The live tail of a run's trace (architecture 10.3, 10.2)."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from charie.runs import service
from charie.runs.events import RecordedEvent, read_events

__all__ = ["TERMINAL_STATUSES", "event_stream", "format_frame"]

#: How often the table is re-read for new rows.
POLL_SECONDS = 1.0

#: Sent when nothing has happened, so the connection is not mistaken for dead by a proxy.
HEARTBEAT_SECONDS = 15.0

#: How long a stream will follow a run that never ends.
MAX_STREAM_SECONDS = 1800.0

#: A run in one of these will produce no further events, so the stream ends.
TERMINAL_STATUSES = service.TERMINAL_STATUSES


def format_frame(event: RecordedEvent) -> str:
    """One event as an SSE frame."""
    payload = json.dumps(
        {"seq": event.seq, "type": event.type, "payload": event.payload, "ts": event.ts.isoformat()}
    )
    return f"id: {event.seq}\nevent: {event.type}\ndata: {payload}\n\n"


def _resume_from(after: int, last_event_id: str | None) -> int:
    """Where to start: the explicit position, or the browser's own bookmark."""
    if after > 0 or not last_event_id:
        return max(0, after)
    try:
        return max(0, int(last_event_id.strip()))
    except ValueError:
        return 0


async def event_stream(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID | None,
    after: int = 0,
    last_event_id: str | None = None,
    poll_seconds: float = POLL_SECONDS,
    max_seconds: float = MAX_STREAM_SECONDS,
) -> AsyncIterator[str]:
    """Everything since ``after``, then everything as it happens, then stop."""
    # Raises `NotFoundError` for a run that is not this caller's.
    seq = _resume_from(after, last_event_id)
    backlog = await service.list_events(org_id=org_id, run_id=run_id, user_id=user_id, after=seq)
    for event in backlog:
        seq = event.seq
        yield format_frame(event)

    loop = asyncio.get_running_loop()
    started = loop.time()
    quiet_since = started

    while True:
        view = await service.get_run(org_id=org_id, run_id=run_id, user_id=user_id)
        finished = view.status in TERMINAL_STATUSES

        # Read after asking whether the run finished.
        fresh = await read_events(org_id=org_id, run_id=run_id, after=seq)
        for event in fresh:
            seq = event.seq
            yield format_frame(event)
        if fresh:
            quiet_since = loop.time()

        if finished:
            return

        now = loop.time()
        if now - started > max_seconds:
            # A stream that has followed a run for half an hour is following a run that is not...
            yield ": stream timed out\n\n"
            return
        if now - quiet_since >= HEARTBEAT_SECONDS:
            yield ": keep-alive\n\n"
            quiet_since = now

        await asyncio.sleep(poll_seconds)
