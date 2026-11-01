"""The answer flow: rounds of starter and planned tasks, then the writer.

Understand once, run up to 4 rounds at the same time, then the writer
turns the checked notebook into 09 blocks with exact copies.
"""

import time
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import select

from charie.chat.analyst.checks import check_body, check_inputs, run_checks
from charie.chat.analyst.context import AnalystContext
from charie.chat.analyst.loop import run_extra_round, run_rounds
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.render import fallback_blocks, render_answer
from charie.chat.analyst.review import review_answer
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
    await _save_answer(ctx, tasks)


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


async def _save_answer(ctx: AnalystContext, tasks: list) -> None:
    """Write, render and save; the notebook view is the fallback."""
    with session_scope() as session:
        message = session.get(Message, ctx.message_id)
        if message is not None:
            message.status = "writing"
            session.commit()
    seq = ctx.log.start("step", "Writing the answer")
    try:
        result = await write_checked_answer(ctx, tasks)
    except AiError:
        result = None
    if result is None:
        ctx.log.finish(seq, status="done", title="Wrote the answer from the notebook.")
        _save_temp_answer(ctx, tasks)
        return
    blocks, shown, fallback = result
    if fallback:
        ctx.log.finish(seq, status="done", title="Wrote the checked numbers.")
        _save_fallback_answer(ctx, tasks, blocks, shown)
        return
    ctx.log.finish(seq, status="done", title="Wrote the answer.")
    _save_blocks(ctx, tasks, blocks, shown)


async def write_checked_answer(ctx: AnalystContext, tasks: list) -> tuple | None:
    """Write, review, check, and fix twice; None when the writer fails.

    Returns the blocks, the shown labels, and whether it is the fallback.
    """
    ran = list(tasks)
    rounds = _round_count(ctx)
    fixes: list[str] = []
    fixes_left = 2
    while True:
        draft = write_answer(ctx, fixes=fixes)
        rendered = render_answer(draft, ctx)
        if rendered is None:
            return None
        blocks, shown = rendered
        review = review_answer(ctx, blocks)
        _review_line(ctx, review)
        inputs = check_inputs(ctx)
        failures = run_checks(draft, blocks, inputs)
        _check_line(ctx, failures, review, inputs)
        if review.verdict == "good" and not failures:
            return blocks, shown, False
        if fixes_left == 0:
            if failures:
                return *fallback_blocks(ctx, failures), True
            return blocks, shown, False
        fixes_left -= 1
        attempt = 2 - fixes_left
        fix_seq = ctx.log.start("step", f"Fixing the answer (try {attempt} of 2)")
        if review.needs_more_data and _extra_round_allowed(ctx, rounds):
            current = await run_extra_round(ctx, ran, rounds + 1, review.missing_data or "")
            ran.extend(current)
            rounds += 1
            fixes = []
        else:
            fixes = [f"{fix.problem}: {fix.how_to_fix}" for fix in review.fixes]
            fixes.extend(failure.message for failure in failures)
        ctx.log.finish(fix_seq, status="done")


def _round_count(ctx: AnalystContext) -> int:
    """How many rounds ran, from their step lines."""
    return sum(
        1
        for line in ctx.log.lines()
        if line.get("kind") == "step" and (line.get("title") or "").startswith("Round ")
    )


def _extra_round_allowed(ctx: AnalystContext, rounds: int) -> bool:
    """Another round needs no Finish, time left, and fewer than 6 rounds."""
    if ctx.state.finish_requested.is_set() or rounds >= 6:
        return False
    minutes = (ctx.settings or {}).get("thinking_minutes", 10)
    return time.monotonic() - ctx.state.started < minutes * 60


def _review_line(ctx: AnalystContext, review) -> None:
    """The reviewer's verdict as a check line."""
    seq = ctx.log.start("check", "Reviewing the answer like a strict manager")
    if review.verdict == "good" and not review.fixes:
        ctx.log.finish(seq, status="done", title="Review: looks good")
        return
    count = len(review.fixes)
    ctx.log.finish(
        seq,
        status="failed",
        title=f"Review: {count} thing" + ("" if count == 1 else "s") + " to fix",
        body="\n".join(f"{fix.problem}: {fix.how_to_fix}" for fix in review.fixes),
    )


def _check_line(ctx: AnalystContext, failures: list, review, inputs) -> None:
    """Every number, claim, quote and chart; failures stay in the details."""
    seq = ctx.log.start("check", "Checking every number, claim, quote and chart")
    details: dict = {"failures": [asdict(failure) for failure in failures]}
    if review.fixes:
        details["review_fixes"] = [fix.model_dump() for fix in review.fixes]
    if not failures:
        ctx.log.finish(seq, status="done", title="Checks passed", details=details)
        return
    count = len(failures)
    ctx.log.finish(
        seq,
        status="failed",
        title=f"Checks found {count} problem" + ("" if count == 1 else "s"),
        body="\n".join(check_body(failures, inputs)),
        details=details,
    )


def _save_fallback_answer(ctx: AnalystContext, tasks: list, blocks: list, shown: list) -> None:
    """The checked numbers and tables when no draft passes."""
    ctx.log.add(
        "note",
        "I couldn't write a fully checked explanation, so I'm showing the checked numbers.",
        "Every number below passed the SQL checker.",
    )
    _save_blocks(ctx, tasks, blocks, shown)


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
