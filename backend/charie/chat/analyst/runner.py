"""One question at a time per chat, in the background (P10.1)."""

import asyncio

from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.context import RunState
from charie.chat.chat_store import build_context, mark_failed
from charie.shared.db import session_scope
from charie.shared.tables.chat import Message

# Every live question, kept until it ends so nothing garbage-collects it.
RUNNING: dict[int, RunState] = {}


async def run_now(message_id: int, state: RunState | None = None) -> None:
    """Run one question to the end. A crash marks it failed, then raises."""
    from charie.chat.analyst.stream import FEEDS

    ctx = build_context(message_id)
    if ctx is None:
        FEEDS.pop(message_id, None)
        return
    ctx.state = state or RunState()
    RUNNING[message_id] = ctx.state
    try:
        await answer_question(ctx)
    except Exception:
        mark_failed(message_id, "Something went wrong while answering. Please ask again.")
        raise
    finally:
        _close_feed(message_id)
        RUNNING.pop(message_id, None)


def _close_feed(message_id: int) -> None:
    """End the stream exactly once: the one `done` carries the last status."""
    from charie.chat.analyst.stream import FEEDS, finish_feed

    feed = FEEDS.get(message_id)
    if feed is None:
        return
    if not feed.has_done():
        with session_scope() as session:
            message = session.get(Message, message_id)
            status = message.status if message is not None else "thinking"
            cost = float(message.cost_usd or 0) if message is not None else 0
        finish_feed(message_id, status=status, cost_usd=cost)
    else:
        finish_feed(message_id)


def start(message_id: int) -> asyncio.Task:
    """Run the question in the background; errors are logged, not raised."""
    from charie.chat.analyst.stream import FEEDS, MessageFeed

    state = RunState()
    RUNNING[message_id] = state
    FEEDS[message_id] = MessageFeed()

    async def _guarded() -> None:
        try:
            await run_now(message_id, state)
        except Exception:
            pass
        finally:
            if RUNNING.get(message_id) is state:
                RUNNING.pop(message_id, None)

    return asyncio.create_task(_guarded())


def request_finish(message_id: int) -> bool:
    """Ask a running question to stop at its next pause. False when idle."""
    state = RUNNING.get(message_id)
    if state is None:
        return False
    state.finish_requested.set()
    return True
