"""The answer flow: rounds of starter and planned tasks, then the writer.

Understand once, run up to 4 rounds at the same time, then the writer
turns the checked notebook into 09 blocks with exact copies.
"""

import asyncio
import time
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import func, select

from charie.chat import chat_store
from charie.chat.analyst.chat_context import (
    FinishedAnswer,
    PendingChoice,
    load_context,
    save_context,
    update_context,
)
from charie.chat.analyst.checks import check_body, check_inputs, run_checks
from charie.chat.analyst.context import AnalystContext
from charie.chat.analyst.loop import run_extra_round, run_rounds
from charie.chat.analyst.notebook import Notebook, QuoteValue
from charie.chat.analyst.render import fallback_blocks, render_answer
from charie.chat.analyst.review import review_answer
from charie.chat.analyst.stream import finish_feed, send_choice, stream_answer
from charie.chat.analyst.write import write_answer
from charie.shared.ai.errors import AiError
from charie.shared.ai.spending import as_utc
from charie.shared.db import session_scope
from charie.shared.tables.chat import Message, QueryRun, ThinkingEvent
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.usage import AiCall

#: One note sentence before the short view; the real writer replaces it.
TEMP_NOTE = "Placeholder answer. Here's what I found:"


#: The not-sure reply when a follow-up points at nothing shown.
NOT_SURE_TEXT = (
    "I'm not sure what you're pointing to in this chat. Please name it, and I'll answer right away."
)


def _deliver_not_sure(ctx: AnalystContext) -> None:
    """One note callout as the whole answer; no rounds ran."""
    ctx.log.add("note", "Asked what to point at instead.")
    blocks = [{"type": "callout", "tone": "note", "text": NOT_SURE_TEXT}]
    _save_blocks(ctx, blocks, [])


#: The failed second choice, in the owner's words.
SETTLE_FAILED_TEXT = "I couldn't settle what you meant. Please ask again in your own words."


def _deliver_choice(ctx: AnalystContext) -> None:
    """One quick question as the whole answer: no rounds, status needs_choice."""
    choice = ctx.understanding.choice
    options = [{"id": option.id, "label": option.label} for option in choice.options]
    saved = {"text": choice.text, "options": options}
    ctx.log.add(
        "decision",
        "Asked you one quick question",
        "This can be read a few ways, so I'd rather ask than guess.",
    )
    send_choice(ctx.message_id, saved)
    _save_blocks(ctx, [], [], status="needs_choice")
    with session_scope() as session:
        message = session.get(Message, ctx.message_id)
        if message is not None and isinstance(message.answer, dict):
            message.answer = {**message.answer, "choice": saved}
        pending = PendingChoice(
            message_id=ctx.message_id, question=ctx.question, text=choice.text, options=options
        )
        pending_context = load_context(session, ctx.chat_id)
        pending_context.pending_choice = pending
        save_context(session, ctx.chat_id, pending_context)
        session.commit()


async def answer_question(ctx: AnalystContext) -> None:
    """Understand once, run the rounds, then write the answer."""
    tasks = await run_rounds(ctx)
    if ctx.choice_failed:
        chat_store.mark_failed(ctx.message_id, SETTLE_FAILED_TEXT)
        return
    if ctx.stop_reason == "needs_choice":
        _deliver_choice(ctx)
        return
    if ctx.unresolved_follow_up:
        _deliver_not_sure(ctx)
        return
    if ctx.state.finish_requested.is_set():
        _deliver_stopped(ctx)
        return
    await _save_answer(ctx, tasks)


def _settle_running_lines(ctx: AnalystContext) -> None:
    """Close every running line, so the panel reads finished."""
    with session_scope() as session:
        seqs = session.scalars(
            select(ThinkingEvent.seq).where(
                ThinkingEvent.message_id == ctx.message_id,
                ThinkingEvent.status == "running",
            )
        ).all()
    for seq in seqs:
        ctx.log.finish(seq, status="done")


def _deliver_stopped(ctx: AnalystContext) -> None:
    """Finish now: the checked fallback when there is one, else a plain stop.

    Without settling, the message stays "thinking", every later question
    is refused, and the stream never sends its terminal event.
    """
    _settle_running_lines(ctx)
    with session_scope() as session:
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        ready = any(
            item.kind in ("number", "table") and item.status == "ok" for item in book.items()
        )
    if not ready:
        with session_scope() as session:
            message = session.get(Message, ctx.message_id)
            if message is not None and message.status == "thinking":
                message.status = "stopped"
                message.finished_at = datetime.now(UTC)
                session.commit()
        finish_feed(ctx.message_id, status="stopped")
        return
    _note_stopped_early(ctx)
    blocks, shown = fallback_blocks(ctx)
    _save_blocks(ctx, blocks, shown, status="stopped")


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
    blocks, shown, fallback, stopped = result
    if stopped:
        ctx.log.finish(seq, status="done", title="Stopped early; showing the checked numbers.")
        _save_blocks(ctx, blocks, shown, status="stopped")
        return
    if fallback:
        ctx.log.finish(seq, status="done", title="Wrote the checked numbers.")
        _save_fallback_answer(ctx, tasks, blocks, shown)
        return
    ctx.log.finish(seq, status="done", title="Wrote the answer.")
    _save_blocks(ctx, blocks, shown)


def _note_stopped_early(ctx: AnalystContext) -> None:
    """The stopped line, shared by both stopped-answer paths."""
    ctx.log.add(
        "note",
        "Stopped early. Showing the checked numbers gathered so far.",
        "Finish now ends the analysis; this is what passed the checks.",
    )


def _stopped_fallback(ctx: AnalystContext) -> tuple:
    """The checked fallback as a stopped answer, never a done one."""
    _note_stopped_early(ctx)
    return *fallback_blocks(ctx, []), True, True


async def write_checked_answer(ctx: AnalystContext, tasks: list) -> tuple | None:
    """Write, review, check, and fix twice; None when the writer fails.

    The two AI calls run in threads, so Finish stays responsive while
    they think. Finish between the calls, or before saving, delivers
    the stopped fallback instead of another rewrite or a done answer.

    Returns the blocks, the shown labels, whether it is the fallback,
    and whether it was stopped.
    """
    ran = list(tasks)
    rounds = _round_count(ctx)
    fixes: list[str] = []
    fixes_left = 2
    while True:
        if ctx.state.finish_requested.is_set():
            return _stopped_fallback(ctx)
        draft = await asyncio.to_thread(write_answer, ctx, fixes)
        if ctx.state.finish_requested.is_set():
            return _stopped_fallback(ctx)
        rendered = render_answer(draft, ctx)
        if rendered is None:
            return None
        blocks, shown = rendered
        ctx.draft = draft
        review = await asyncio.to_thread(review_answer, ctx, blocks)
        if ctx.state.finish_requested.is_set():
            return _stopped_fallback(ctx)
        _review_line(ctx, review)
        inputs = check_inputs(ctx)
        failures = run_checks(draft, blocks, inputs)
        _check_line(ctx, failures, review, inputs)
        if ctx.state.finish_requested.is_set():
            return _stopped_fallback(ctx)
        if review.verdict == "good" and not failures:
            return blocks, shown, False, False
        if fixes_left == 0:
            if failures:
                return *fallback_blocks(ctx, failures), True, False
            return blocks, shown, False, False
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
    _save_blocks(ctx, blocks, shown)


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
    _save_blocks(ctx, blocks, [])


def _kb_number(ctx: AnalystContext) -> int:
    """The version's number for the saved answer (the id when unknown)."""
    with session_scope() as session:
        number = session.scalar(select(KbVersion.number).where(KbVersion.id == ctx.kb_version_id))
    return number if number is not None else ctx.kb_version_id


def _seconds_between(started, finished) -> int:
    """Whole seconds between two stamps, never negative."""
    if started is None:
        return 0
    return max(0, int((as_utc(finished) - as_utc(started)).total_seconds()))


def _consulted_documents(session, ctx: AnalystContext) -> set:
    """Every document the notebook quotes for this message."""
    documents = set()
    book = Notebook.load(session, ctx.message_id, ctx.chat_id)
    for item in book.items():
        if item.kind == "quote":
            document_id = QuoteValue.model_validate(item.value).document_id
            if document_id is not None:
                documents.add(document_id)
    return documents


def _save_blocks(
    ctx: AnalystContext,
    blocks: list[dict],
    shown: list[str],
    status: str = "done",
) -> None:
    """Save the answer, its real totals and terminal status, then stream.

    The save lands before any stream event: reload and streamed
    completion always show the same answer and totals.
    """
    answer = {
        "message_id": ctx.message_id,
        "kb_version": _kb_number(ctx),
        "data_through": ctx.data_through.isoformat() if ctx.data_through is not None else None,
        "blocks": blocks,
    }
    with session_scope() as session:
        cleared = load_context(session, ctx.chat_id)
        if cleared.pending_choice is not None:
            cleared.pending_choice = None
            save_context(session, ctx.chat_id, cleared)
        message = session.get(Message, ctx.message_id)
        if message is None:
            return
        finished = datetime.now(UTC)
        message.answer = answer
        message.status = status
        message.finished_at = finished
        started = message.started_at
        message.seconds = _seconds_between(started, finished)
        message.steps = session.scalar(
            select(func.count(ThinkingEvent.id)).where(ThinkingEvent.message_id == ctx.message_id)
        )
        message.queries = session.scalar(
            select(func.count(QueryRun.id)).where(QueryRun.message_id == ctx.message_id)
        )
        message.documents = len(_consulted_documents(session, ctx))
        cost = session.scalar(
            select(func.coalesce(func.sum(AiCall.cost_usd), 0)).where(
                AiCall.message_id == ctx.message_id
            )
        )
        message.cost_usd = float(cost or 0)
        session.commit()
        summary = {
            "seconds": message.seconds,
            "steps": message.steps,
            "queries": message.queries,
            "documents": message.documents,
        }
        saved_cost = float(message.cost_usd or 0)
        if shown:
            Notebook.load(session, ctx.message_id, ctx.chat_id).mark_shown(shown)
        if status == "done":
            try:
                _save_chat_context(session, ctx, message.id, blocks, shown)
            except Exception as err:
                ctx.log.add("note", "The chat memory did not save.", str(err))
    stream_answer(ctx.message_id, blocks, summary)
    finish_feed(ctx.message_id, status=status, cost_usd=saved_cost)


def _save_chat_context(
    session, ctx: AnalystContext, message_id: int, blocks: list, shown: list[str]
) -> None:
    """Fold this done answer into the chat memory, in the same transaction."""
    book = Notebook.load(session, ctx.message_id, ctx.chat_id)
    understanding = ctx.understanding
    style = (ctx.settings or {}).get("number_format", "short")
    data_through = ctx.data_through
    if hasattr(data_through, "isoformat"):
        data_through = data_through.isoformat()
    draft = getattr(ctx, "draft", None)
    resolved = getattr(ctx.periods, "periods", None)
    if resolved is None:
        resolved = ctx.periods or []
    finished = FinishedAnswer(
        message_id=message_id,
        question=ctx.question,
        kind=getattr(understanding, "kind", "") or "",
        asks=[ask.model_dump(mode="json") for ask in getattr(understanding, "asks", []) or []],
        filters=[
            filt.model_dump(mode="json") for filt in getattr(understanding, "filters", []) or []
        ],
        periods=[
            {
                "label": period.label,
                "expression": period.expression.model_dump(mode="json")
                if hasattr(period.expression, "model_dump")
                else str(period.expression),
                "start": period.start.isoformat()
                if hasattr(period.start, "isoformat")
                else str(period.start),
                "end": period.end.isoformat()
                if hasattr(period.end, "isoformat")
                else str(period.end),
                "text": period.text,
            }
            for period in resolved
        ],
        used_labels=list(shown),
        items=[item.model_dump(mode="json") for item in book.items()],
        draft=draft.model_dump(mode="json")
        if draft is not None and hasattr(draft, "model_dump")
        else {"blocks": []},
        blocks=list(blocks),
        data_through=str(data_through or ""),
        kb_version=ctx.kb_version_id,
        style=style,
    )
    save_context(session, ctx.chat_id, update_context(load_context(session, ctx.chat_id), finished))
