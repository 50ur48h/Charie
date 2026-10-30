"""The live feed: stored event lines and the server-sent stream (P07.1)."""

import json
import time
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.learner.steps.base import STEP_NUMBERS
from charie.shared.tables.learning import LearningEvent, LearningRun

KEEPALIVE = ": keep-alive\n\n"
POLL_SECONDS = 1.0
KEEPALIVE_EVERY = 15


def add_event(
    session: Session,
    run_id: int,
    kind: str,
    message: str,
    step: str | None = None,
    details: dict | None = None,
) -> LearningEvent:
    """Write one feed line; its id is the stream's durable sequence number."""
    event = LearningEvent(
        run_id=run_id, step=step, kind=kind, message=message, details=details or {}
    )
    session.add(event)
    session.flush()
    return event


def events_since(session: Session, run_id: int, last_id: int) -> list[LearningEvent]:
    """Stored lines after an id, oldest first (replay after a reconnect)."""
    return list(
        session.scalars(
            select(LearningEvent)
            .where(LearningEvent.run_id == run_id, LearningEvent.id > last_id)
            .order_by(LearningEvent.id)
        )
    )


def event_data(event: LearningEvent) -> dict:
    """The `event` line the screens expect: seq, at, step, kind, message."""
    return {
        "seq": event.id,
        "at": event.at.isoformat(),
        "step": STEP_NUMBERS.get(event.step or "", 0),
        "kind": event.kind,
        "message": event.message,
    }


def progress_data(run: LearningRun) -> dict:
    """The `progress` line: step number, done and total jobs, percent."""
    steps = run.progress.get("steps", {})
    done = sum(entry.get("done", 0) for entry in steps.values())
    total = sum(entry.get("total", 0) for entry in steps.values())
    return {
        "step": STEP_NUMBERS.get(run.step or "", 0),
        "done": done,
        "total": total,
        "percent": round(done / total * 100) if total else 0,
    }


def format_sse(seq: int | None, name: str, data: dict) -> str:
    """One server-sent line: optional id, event name and JSON data."""
    head = f"id: {seq}\n" if seq is not None else ""
    return f"{head}event: {name}\ndata: {json.dumps(data, sort_keys=True)}\n\n"


def feed_lines(
    make_session, run_id: int, last_id: int = 0, limit: int | None = None
) -> Iterator[str]:
    """Replay missed lines, then poll for new ones, progress, status, keepalives.

    `make_session` opens a fresh session per poll so reconnects and restarts
    see every stored line. `limit` bounds the lines for tests; the endpoint
    passes None and streams until the client goes away.
    """
    sent = 0
    seen = last_id
    last_progress: dict | None = None
    last_status: str | None = None
    quiet_polls = 0
    while True:
        with make_session() as session:
            batch = [(event.id, event_data(event)) for event in events_since(session, run_id, seen)]
            run = session.get(LearningRun, run_id)
            progress = progress_data(run) if run is not None else None
            status = run.status if run is not None else None
        changed = False
        for seq, data in batch:
            yield format_sse(seq, "event", data)
            seen = seq
            sent += 1
            changed = True
            if limit is not None and sent >= limit:
                return
        if progress is not None and progress != last_progress:
            yield format_sse(None, "progress", progress)
            last_progress = progress
            sent += 1
            changed = True
            if limit is not None and sent >= limit:
                return
        if status is not None and status != last_status:
            yield format_sse(None, "status", {"status": status})
            last_status = status
            sent += 1
            changed = True
            if limit is not None and sent >= limit:
                return
        if changed:
            quiet_polls = 0
        else:
            if limit is not None:
                return
            quiet_polls += 1
            if quiet_polls >= KEEPALIVE_EVERY:
                yield KEEPALIVE
                quiet_polls = 0
        time.sleep(POLL_SECONDS)
