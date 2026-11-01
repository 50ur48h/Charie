"""One question at a time per chat, in the background (P10.1)."""

import asyncio

from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.context import RunState
from charie.chat.chat_store import build_context, mark_failed

# Every live question, kept until it ends so nothing garbage-collects it.
RUNNING: dict[int, RunState] = {}


async def run_now(message_id: int, state: RunState | None = None) -> None:
    """Run one question to the end. A crash marks it failed, then raises."""
    ctx = build_context(message_id)
    if ctx is None:
        return
    ctx.state = state or RunState()
    RUNNING[message_id] = ctx.state
    try:
        await answer_question(ctx)
    except Exception:
        mark_failed(message_id, "Something went wrong while answering. Please ask again.")
        raise
    finally:
        RUNNING.pop(message_id, None)


def start(message_id: int) -> asyncio.Task:
    """Run the question in the background; errors are logged, not raised."""
    state = RunState()
    RUNNING[message_id] = state

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
