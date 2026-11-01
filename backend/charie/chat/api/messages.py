"""Message addresses: Finish now and the live stream (P10.1, P10.2)."""

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from charie.chat import chat_store
from charie.chat.analyst.runner import request_finish
from charie.chat.analyst.stream import FEEDS, StreamEvent
from charie.shared.db import get_session, session_scope
from charie.shared.errors import ApiError
from charie.shared.tables.chat import Message, ThinkingEvent

messages_router = APIRouter()


@messages_router.post("/api/messages/{message_id}/finish")
def finish_now(message_id: int, session: Session = Depends(get_session)) -> dict:
    """Stop a running question at its next pause. A finished one refuses."""
    message = chat_store.get_message(session, message_id)
    if message.role != "assistant":
        raise ApiError(404, "not_found", "That message doesn't exist.")
    if message.status not in ("thinking", "writing"):
        raise ApiError(409, "not_running", "This question has already finished.")
    request_finish(message_id)
    return {"finished": True, "message_id": message_id}


def _sse(item: StreamEvent) -> dict:
    """One feed event as the wire format: id, name, JSON data."""
    return {"event": item.event, "id": str(item.id), "data": json.dumps(item.data)}


def _last_event_id(request: Request) -> int:
    """The client's Last-Event-ID, or 0 when missing or not a number."""
    try:
        return int(request.headers.get("last-event-id", "0"))
    except (TypeError, ValueError):
        return 0


async def _live_events(message_id: int, after_id: int):
    """Stored events above the client's id, then follow until done."""
    feed = FEEDS.get(message_id)
    if feed is None:
        return
    done_ids = [item.id for item in feed.events if item.event == "done"]
    if done_ids and done_ids[0] <= after_id:
        return
    async for item in feed.follow(after_id):
        yield _sse(item)


def _rebuilt_events(message_id: int, thinking: list[dict], summary: dict, done: dict):
    """The saved state as a fresh stream: reset, thinking, summary, done.

    Numbering restarts at 1, so the client's stale live cursor cannot
    apply: the reset tells it to drop that cursor and the partial live
    buffer first. The snapshot always ends in the terminal done, however
    high the client's Last-Event-ID is.
    """
    yield {"event": "reset", "id": "0", "data": json.dumps({"message_id": message_id})}
    next_id = 0
    for line in thinking:
        next_id += 1
        yield {"event": "thinking", "id": str(next_id), "data": json.dumps(line)}
    next_id += 1
    yield {"event": "summary", "id": str(next_id), "data": json.dumps(summary)}
    next_id += 1
    yield {"event": "done", "id": str(next_id), "data": json.dumps(done)}


@messages_router.get("/api/messages/{message_id}/stream")
async def stream_message(message_id: int, request: Request) -> EventSourceResponse:
    """The live stream: thinking and the answer as they happen (P10.2).

    A reconnect sends only what was missed after Last-Event-ID. A
    finished question, or an app restart, rebuilds the stream from the
    database instead — blocks are not re-sent; on `done` the screen loads
    the saved answer. Never holds a database session while waiting.
    """
    with session_scope() as session:
        message = session.get(Message, message_id)
        if message is None or message.role != "assistant":
            raise ApiError(404, "not_found", "That message doesn't exist.")
        thinking = [
            {
                "seq": row.seq,
                "kind": row.kind,
                "status": row.status,
                "title": row.title,
                "body": row.body,
                "details": row.details,
            }
            for row in session.scalars(
                select(ThinkingEvent)
                .where(ThinkingEvent.message_id == message_id)
                .order_by(ThinkingEvent.seq)
            ).all()
        ]
        summary = {
            "seconds": message.seconds,
            "steps": message.steps,
            "queries": message.queries,
            "documents": message.documents,
        }
        done = {
            "message_id": message.id,
            "status": message.status,
            "cost_usd": float(message.cost_usd or 0),
        }
    if message_id in FEEDS:
        events = _live_events(message_id, _last_event_id(request))
    else:
        # A restart or an expired feed starts numbering over; the
        # client's cursor belongs to the old numbering and is reset by
        # the first event, so it is never applied here.
        events = _rebuilt_events(message_id, thinking, summary, done)
    return EventSourceResponse(events, ping=15)
