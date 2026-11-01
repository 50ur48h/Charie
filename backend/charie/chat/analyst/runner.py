"""One question at a time per chat, in the background (P10.1)."""

import asyncio

from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.context import RunState
from charie.chat.chat_store import build_context, mark_failed
from charie.shared.db import session_scope
from charie.shared.tables.chat import Message

# Every live question, kept until it ends so nothing garbage-collects it.
RUNNING: dict[int, RunState] = {}


async def run_now(message_id: int, state: RunState | None = None, private: bool = False) -> None:
    """Run one question to the end. A crash marks it failed, then raises."""
    from charie.chat.analyst.stream import FEEDS

    ctx = build_context(message_id, private=private)
    if ctx is None:
        FEEDS.pop(message_id, None)
        return
    ctx.state = state or RunState()
    ctx.remember = ctx.state.remember
    ctx.name_chat = ctx.state.name_chat
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


def _extract_after_done(message_id: int, state: RunState) -> None:
    """Save lasting preferences after a done answer; never fails loudly."""
    import logging

    if not state.remember:
        return
    with session_scope() as session:
        from sqlalchemy import select

        assistant = session.get(Message, message_id)
        if assistant is None or assistant.status != "done":
            return
        user = session.scalars(
            select(Message)
            .where(
                Message.chat_id == assistant.chat_id,
                Message.role == "user",
                Message.status == "done",
            )
            .order_by(Message.id.desc())
        ).first()
        if user is None:
            return
        try:
            from charie.chat.memory import extract_and_save_memories

            extract_and_save_memories(session, user)
        except Exception as err:
            logging.getLogger(__name__).warning("memory extraction failed: %s", err)
            session.rollback()


def start(message_id: int, remember: bool = True, name_chat: bool = True) -> asyncio.Task:
    """Run the question in the background; errors are logged, not raised."""
    from charie.chat.analyst.stream import FEEDS, MessageFeed

    state = RunState(remember=remember, name_chat=name_chat)
    RUNNING[message_id] = state
    FEEDS[message_id] = MessageFeed()

    async def _guarded() -> None:
        try:
            await run_now(message_id, state)
        except Exception:
            pass
        else:
            await asyncio.to_thread(_extract_after_done, message_id, state)
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
