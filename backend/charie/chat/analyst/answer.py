"""The answer flow: the placeholder until the real analyst lands (P10.1)."""

import asyncio
from datetime import UTC, datetime

from charie.chat.analyst.context import AnalystContext
from charie.shared.db import session_scope
from charie.shared.tables.chat import Message

# Seconds between placeholder lines; tests set it to 0.
PLACEHOLDER_PAUSE = 1.0

PLACEHOLDER_BODY = "This is a placeholder answer. The real analyst arrives in the next sub-phases."


async def answer_question(ctx: AnalystContext) -> None:
    """Three placeholder lines, then the placeholder answer.

    A Finish now click skips the rest. Later sub-phases swap this body
    for the real analyst; the runner and the store stay the same.
    """
    steps = [
        ("step", "Reading your question", ""),
        ("step", "Placeholder: the real analyst is being built", ""),
        ("check", "Placeholder check", ""),
    ]
    for kind, title, body in steps:
        if ctx.state.finish_requested.is_set():
            return
        seq = ctx.log.start(kind, title, body)
        await asyncio.sleep(PLACEHOLDER_PAUSE)
        if ctx.state.finish_requested.is_set():
            ctx.log.finish(seq, status="done")
            return
        ctx.log.finish(seq, status="done")
    _save_placeholder_answer(ctx)


def _save_placeholder_answer(ctx: AnalystContext) -> None:
    """One note sentence as the whole answer; same shape as real answers."""
    answer = {
        "message_id": ctx.message_id,
        "kb_version": ctx.kb_version_id,
        "data_through": ctx.data_through.isoformat() if ctx.data_through is not None else None,
        "blocks": [
            {
                "kind": "text",
                "sentences": [
                    {
                        "kind": "note",
                        "text": PLACEHOLDER_BODY,
                        "proofs": [],
                    }
                ],
            }
        ],
    }
    with session_scope() as session:
        message = session.get(Message, ctx.message_id)
        if message is None:
            return
        message.answer = answer
        message.status = "done"
        message.finished_at = datetime.now(UTC)
        session.commit()
