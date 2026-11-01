"""The answer flow: rounds of starter and planned tasks, then a placeholder.

Understand once, run up to 4 rounds at the same time, then a placeholder
answer with the notebook's short view. P10.10 replaces the placeholder
with the real writer.
"""

import time
from datetime import UTC, datetime

from sqlalchemy import select

from charie.chat.analyst.context import AnalystContext
from charie.chat.analyst.loop import run_rounds
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.stream import FEEDS, finish_feed
from charie.shared.db import session_scope
from charie.shared.tables.chat import Message, ThinkingEvent

#: One note sentence before the short view; the real writer replaces it.
TEMP_NOTE = "Placeholder answer. Here's what I found:"


def _emit_temp_events(ctx: AnalystContext, tasks: list, sentences: list[dict]) -> None:
    """The saved answer through the live stream: summary, block, text, done.

    The wire shape matches the real rounds (P10.2): one empty text block
    first, then one text event with all its text.
    """
    feed = FEEDS.get(ctx.message_id)
    if feed is None or feed.closed:
        return
    seconds = int(time.monotonic() - ctx.state.started)
    feed.add(
        "summary",
        {
            "seconds": seconds,
            "steps": len(ctx.log.lines()),
            "queries": len(tasks),
            "documents": 0,
        },
    )
    feed.add("block", {"index": 0, "block": {"type": "text", "paragraphs": []}})
    feed.add(
        "text",
        {
            "index": 0,
            "delta": "\n".join(sentence["text"] for sentence in sentences),
        },
    )


async def answer_question(ctx: AnalystContext) -> None:
    """Understand once, run the rounds, then the temp answer."""
    tasks = await run_rounds(ctx)
    if ctx.state.finish_requested.is_set():
        _mark_stopped(ctx)
        return
    _save_temp_answer(ctx, tasks)


def _mark_stopped(ctx: AnalystContext) -> None:
    """Finish now: settle running lines and stop the message.

    Without this the message stays "thinking", every later question is
    refused, and the stream never sends its terminal event.
    """
    with session_scope() as session:
        seqs = session.scalars(
            select(ThinkingEvent.seq).where(
                ThinkingEvent.message_id == ctx.message_id,
                ThinkingEvent.status == "running",
            )
        ).all()
    for seq in seqs:
        ctx.log.finish(seq, status="done")
    with session_scope() as session:
        message = session.get(Message, ctx.message_id)
        if message is not None and message.status == "thinking":
            message.status = "stopped"
            message.finished_at = datetime.now(UTC)
            session.commit()
    finish_feed(ctx.message_id, status="stopped")


def _save_temp_answer(ctx: AnalystContext, tasks: list) -> None:
    """One note sentence plus the notebook's short view, as real answers.

    The view reads through a fresh session: the notebook must never
    outlive its session, or its bare reads hold a transaction open and
    block the next truncate.
    """
    with session_scope() as session:
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        short = book.short_view()
    sentences = [
        {"kind": "note", "text": TEMP_NOTE, "proofs": []},
        {"kind": "note", "text": short, "proofs": []},
    ]
    answer = {
        "message_id": ctx.message_id,
        "kb_version": ctx.kb_version_id,
        "data_through": ctx.data_through.isoformat() if ctx.data_through is not None else None,
        "blocks": [{"kind": "text", "sentences": sentences}],
    }
    with session_scope() as session:
        message = session.get(Message, ctx.message_id)
        if message is None:
            return
        message.answer = answer
        message.status = "done"
        message.finished_at = datetime.now(UTC)
        session.commit()
    ctx.log.add("note", TEMP_NOTE, "Here's what I found.")
    _emit_temp_events(ctx, tasks, sentences)
    finish_feed(ctx.message_id, status="done")
