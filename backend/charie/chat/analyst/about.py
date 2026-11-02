"""About an answer, and not-in-the-data replies (P11.6).

The about reply is written by code from the earlier answer's
notebook: no new queries, no writer, no review and no checks. The
not-in-data reply runs one document search; with checked quotes it
writes normally, without them code says so plainly.
"""

from sqlalchemy import select

from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.render import limited_method
from charie.chat.analyst.understand import ABOUT_RE
from charie.shared.db import session_scope
from charie.shared.tables.chat import Message

#: No earlier done answer to explain.
NO_EARLIER_TEXT = "There's no earlier answer in this chat to explain yet."

#: The fixed lines of an about reply.
ABOUT_TITLE = "Looked up how I worked it out"
ABOUT_BODY = "Used my notes from the earlier answer. No new queries were needed."

#: The document search found nothing to quote.
NOTHING_TEXT = "I didn't find anything about it in your documents either."


def _missing_callout(missing: str) -> str:
    """The first block of a not-in-data reply, in the owner's words."""
    return f"Your data doesn't have {missing}, so I can't work it out from the numbers."


def _parse_about_refs(about) -> list[tuple[int, str]]:
    """(message id, label) pairs from the valid about refs."""
    refs = []
    for ref in about or []:
        if ABOUT_RE.match(ref or "") is None:
            continue
        head, _, label = (ref or "").partition(":")
        refs.append((int(head), label))
    return refs


def _earlier_done(session, chat_id: int, before_id: int):
    """Earlier done assistant messages, newest first."""
    return session.scalars(
        select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.role == "assistant",
            Message.status == "done",
            Message.id < before_id,
        )
        .order_by(Message.id.desc())
    ).all()


def _about_target(session, ctx):
    """(message id, labels or None): the answer to explain.

    Refs name one earlier message and label, like 812:n1. Refs that
    match nothing explain the whole last answer.
    """
    candidates = _earlier_done(session, ctx.chat_id, ctx.message_id)
    if not candidates:
        return None
    wanted = _parse_about_refs(ctx.understanding.about or [])
    if not wanted:
        return candidates[0].id, None
    for message in candidates:
        labels = [label for (mid, label) in wanted if mid == message.id]
        if not labels:
            continue
        have = {
            item.label
            for item in Notebook.load(session, message.id, ctx.chat_id).items()
            if item.kind == "number"
        }
        kept = [label for label in labels if label in have]
        if kept:
            return message.id, kept
    return candidates[0].id, None


def _earlier_answer(session, message):
    """The saved answer dict of one earlier message, or {}."""
    answer = message.answer if message is not None else None
    return answer if isinstance(answer, dict) else {}


def answer_about(ctx) -> None:
    """Explain the earlier answer from its notebook; code only."""
    from charie.chat.analyst.answer import _save_blocks

    ctx.log.add("step", ABOUT_TITLE, ABOUT_BODY)
    with session_scope() as session:
        target = _about_target(session, ctx)
        stored_version = None
        stored_through = None
        kb_ref = ctx.kb_version_id
        if target is not None:
            message = session.get(Message, target[0])
            earlier = _earlier_answer(session, message)
            stored_version = earlier.get("kb_version")
            stored_through = earlier.get("data_through")
            kb_ref = stored_version
            if kb_ref is None and message is not None:
                kb_ref = message.kb_version_id or ctx.kb_version_id
    if target is None:
        _save_blocks(
            ctx,
            [{"type": "callout", "tone": "note", "text": NO_EARLIER_TEXT}],
            [],
            keep_context=False,
        )
        return
    message_id, labels = target
    style = (ctx.settings or {}).get("number_format", "short")
    with session_scope() as session:
        method, shown = limited_method(session, message_id, ctx.chat_id, kb_ref, labels, style)
    if labels is not None and len(shown) == 1:
        line = f"Here's how I worked out {shown[0]['text']}, {shown[0]['description']}."
    else:
        line = "Here's how I worked out my last answer."
    blocks = [
        {"type": "text", "paragraphs": [{"sentences": [{"kind": "note", "text": line}]}]},
        method,
    ]
    _save_blocks(
        ctx,
        blocks,
        [],
        keep_context=False,
        kb_version=stored_version,
        data_through=stored_through,
    )


async def answer_not_in_data(ctx, tasks) -> None:
    """One document search, then quotes write normally or code says none."""
    from charie.chat.analyst.answer import _save_answer, _save_blocks

    missing = (ctx.understanding.missing or "").strip() or "that"
    ctx.log.add(
        "decision",
        "Not in your data",
        f"Your data doesn't have {missing}. Checking your documents instead.",
    )
    with session_scope() as session:
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        quotes = [item for item in book.items() if item.kind == "quote"]
    if not quotes:
        blocks = [
            {
                "type": "callout",
                "tone": "note",
                "text": _missing_callout(missing),
            },
            {
                "type": "text",
                "paragraphs": [{"sentences": [{"kind": "note", "text": NOTHING_TEXT}]}],
            },
        ]
        _save_blocks(ctx, blocks, [], keep_context=False)
        return
    await _save_answer(
        ctx,
        tasks,
        instruction="Say what the documents say about it, quoting them. Don't estimate the number.",
    )
