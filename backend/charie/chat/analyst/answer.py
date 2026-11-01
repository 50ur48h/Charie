"""The answer flow: rounds of starter and planned tasks, then the writer.

Understand once, run up to 4 rounds at the same time, then the writer
turns the checked notebook into 09 blocks with exact copies.
"""

import time
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select

from charie.chat.analyst.checks import check_inputs, run_checks
from charie.chat.analyst.context import AnalystContext
from charie.chat.analyst.loop import run_rounds
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.render import render_answer
from charie.chat.analyst.stream import FEEDS, finish_feed
from charie.chat.analyst.write import write_answer
from charie.shared.ai.errors import AiError
from charie.shared.db import session_scope
from charie.shared.tables.chat import Message, ThinkingEvent
from charie.shared.tables.knowledge import KbVersion

#: One note sentence before the short view; the real writer replaces it.
TEMP_NOTE = "Placeholder answer. Here's what I found:"


def _emit_temp_events(ctx: AnalystContext, tasks: list, blocks: list[dict]) -> None:
    """The saved answer through the live stream: summary, blocks, text, done.

    The wire shape matches the real rounds (P10.2): text blocks arrive
    empty, then fill with text events; other blocks arrive whole.
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
    for index, block in enumerate(blocks):
        if block.get("type") == "text":
            feed.add("block", {"index": index, "block": {"type": "text", "paragraphs": []}})
            feed.add(
                "text",
                {
                    "index": index,
                    "delta": "\n".join(
                        sentence["text"]
                        for paragraph in block.get("paragraphs", [])
                        for sentence in paragraph.get("sentences", [])
                    ),
                },
            )
        else:
            feed.add("block", {"index": index, "block": block})


async def answer_question(ctx: AnalystContext) -> None:
    """Understand once, run the rounds, then write the answer."""
    tasks = await run_rounds(ctx)
    if ctx.state.finish_requested.is_set():
        _mark_stopped(ctx)
        return
    _save_answer(ctx, tasks)


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


def _save_answer(ctx: AnalystContext, tasks: list) -> None:
    """Write, render and save; the notebook view is the fallback."""
    with session_scope() as session:
        message = session.get(Message, ctx.message_id)
        if message is not None:
            message.status = "writing"
            session.commit()
    seq = ctx.log.start("step", "Writing the answer")
    try:
        draft = write_answer(ctx)
        rendered = render_answer(draft, ctx)
    except AiError:
        draft = None
        rendered = None
    if rendered is None:
        ctx.log.finish(seq, status="done", title="Wrote the answer from the notebook.")
        _save_temp_answer(ctx, tasks)
        return
    ctx.log.finish(seq, status="done", title="Wrote the answer.")
    _run_checks(ctx, draft, rendered[0])
    _save_blocks(ctx, tasks, *rendered)


def _run_checks(ctx: AnalystContext, draft, blocks: list[dict]) -> None:
    """Check every number, label and claim; a failure still shows the answer.

    The review loop (P10.12) retries failures; until then the answer is
    shown with a failed check line.
    """
    seq = ctx.log.start("check", "Checking every number, label and claim")
    failures = run_checks(draft, blocks, check_inputs(ctx))
    if not failures:
        ctx.log.finish(seq, status="done", title="Checks passed")
        return
    count = len(failures)
    ctx.log.finish(
        seq,
        status="failed",
        title=f"Checks found {count} problem" + ("" if count == 1 else "s"),
        body="\n".join(failure.message for failure in failures),
        details={"failures": [asdict(failure) for failure in failures]},
    )


def _save_temp_answer(ctx: AnalystContext, tasks: list) -> None:
    """One note sentence plus the notebook's short view, as real answers.

    The view reads through a fresh session: the notebook must never
    outlive its session, or its bare reads hold a transaction open and
    block the next truncate.
    """
    with session_scope() as session:
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        short = book.short_view()
    blocks = [
        {
            "type": "text",
            "paragraphs": [
                {
                    "sentences": [
                        {"kind": "note", "text": TEMP_NOTE},
                        {"kind": "note", "text": short},
                    ]
                }
            ],
        }
    ]
    ctx.log.add("note", TEMP_NOTE, "Here's what I found.")
    _save_blocks(ctx, tasks, blocks, [])


def _kb_number(ctx: AnalystContext) -> int:
    """The version's number for the saved answer (the id when unknown)."""
    with session_scope() as session:
        number = session.scalar(select(KbVersion.number).where(KbVersion.id == ctx.kb_version_id))
    return number if number is not None else ctx.kb_version_id


def _save_blocks(ctx: AnalystContext, tasks: list, blocks: list[dict], shown: list[str]) -> None:
    """Save the answer blocks and settle the message and stream."""
    answer = {
        "message_id": ctx.message_id,
        "kb_version": _kb_number(ctx),
        "data_through": ctx.data_through.isoformat() if ctx.data_through is not None else None,
        "blocks": blocks,
    }
    with session_scope() as session:
        message = session.get(Message, ctx.message_id)
        if message is None:
            return
        message.answer = answer
        message.status = "done"
        message.finished_at = datetime.now(UTC)
        session.commit()
        if shown:
            Notebook.load(session, ctx.message_id, ctx.chat_id).mark_shown(shown)
    _emit_temp_events(ctx, tasks, blocks)
    finish_feed(ctx.message_id, status="done")
