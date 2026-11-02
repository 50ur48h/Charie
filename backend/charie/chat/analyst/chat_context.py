"""Each chat's memory: what we're looking at, shown and still open (P11.1).

The context is plain JSON on the chat row. Code builds it from the draft
and the notebook after every done answer; the AI never writes it.
"""

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from charie.chat.analyst.labels import fill_labels
from charie.chat.analyst.render import values_for
from charie.shared.tables.chat import Chat


class Focus(BaseModel):
    """The question just asked and how Charie read it."""

    message_id: int = 0
    question: str = ""
    kind: str = ""
    asks: list[dict] = Field(default=[])
    filters: list[dict] = Field(default=[])
    periods: list[dict] = Field(default=[])


class ShownList(BaseModel):
    """One comparison list the owner saw, newest last."""

    message_id: int = 0
    title: str = ""
    dimension: str | None = None
    items: list[str] = Field(default=[])


class SaidFact(BaseModel):
    """One number the owner saw, in the words it was shown in.

    `ref` is the message id and label, like `812:n1`, so two
    messages can use n1 for different facts.
    """

    ref: str = ""
    key: str = "{}"
    description: str = ""
    text: str = ""
    value: str = ""
    unit: str = ""
    currency: str = ""
    data_through: str = ""
    kb_version: int = 0


class OpenReason(BaseModel):
    """One possible reason the answer offered but did not settle."""

    message_id: int = 0
    text: str = ""
    labels: list[str] = Field(default=[])


class PendingChoice(BaseModel):
    """The waiting quick question: set on needs_choice, cleared next answer."""

    message_id: int = 0
    question: str = ""
    text: str = ""
    options: list[dict] = Field(default=[])


class ChatContext(BaseModel):
    """The whole chat memory; every field has a default, so old chats load."""

    focus: Focus | None = None
    lists: list[ShownList] = Field(default=[])
    said: list[SaidFact] = Field(default=[])
    open_reasons: list[OpenReason] = Field(default=[])
    pending_choice: PendingChoice | None = None


class FinishedAnswer(BaseModel):
    """What the context saver needs from one done answer."""

    message_id: int = 0
    question: str = ""
    kind: str = ""
    asks: list[dict] = Field(default=[])
    filters: list[dict] = Field(default=[])
    periods: list[dict] = Field(default=[])
    used_labels: list[str] = Field(default=[])
    items: list[dict] = Field(default=[])
    draft: dict = Field(default={"blocks": []})
    blocks: list[dict] = Field(default=[])
    data_through: str = ""
    kb_version: int = 0
    style: str = "short"


def _focus_line(focus: Focus | None) -> str:
    """What the last question asked, in the AI's own key words."""
    if focus is None:
        return ""
    parts: list[str] = []
    asks = [
        str(ask.get("metric_key") or ask.get("new_metric") or "").replace("_", " ")
        for ask in focus.asks
    ]
    asks = [ask for ask in asks if ask]
    if asks:
        parts.append("; ".join(asks))
    splits = sorted({split for ask in focus.asks for split in ask.get("split_by", [])})
    if splits:
        parts.append("by " + ", ".join(str(split).replace("_", " ") for split in splits))
    for filt in focus.filters:
        values = ", ".join(str(value) for value in filt.get("values", []))
        if values:
            parts.append(values)
    texts = [str(period.get("text", "")) for period in focus.periods]
    parts.extend(text for text in texts if text)
    if not parts:
        return ""
    return "Looking at: " + "; ".join(parts)


def _pending_line(pending: PendingChoice | None) -> str:
    """The waiting quick question, so a typed reply reads through it."""
    if pending is None:
        return ""
    labels = ", ".join(str(option.get("label", "")) for option in pending.options)
    return f"Waiting quick question: {pending.text} Options: {labels}."


def context_for_prompt(context: ChatContext) -> str:
    """The chat memory as plain text for the understand prompt (P11.2).

    Newest lists first; an empty context gives an empty view.
    """
    lines: list[str] = []
    pending_line = _pending_line(context.pending_choice)
    if pending_line:
        lines.append(pending_line)
    focus_line = _focus_line(context.focus)
    if focus_line:
        lines.append(focus_line)
    for pos, shown in enumerate(reversed(context.lists[-3:]), start=1):
        newest = " (newest)" if pos == 1 else ""
        head = f'List {pos}{newest}, "{shown.title}"'
        if shown.dimension:
            head += f" ({shown.dimension})"
        items = [f"{num}. {item}" for num, item in enumerate(shown.items[:20], start=1)]
        lines.append(head + (": " + " ".join(items) if items else ""))
    said = context.said[-20:]
    if said:
        shown_said = " ".join(f"[{fact.ref}] {fact.description} = {fact.text};" for fact in said)
        lines.append("Already said: " + shown_said)
    if context.open_reasons:
        lines.append(
            "Possible reasons still open: "
            + "; ".join(reason.text for reason in context.open_reasons)
        )
    return "\n".join(lines)


def fact_key_text(item: dict) -> str:
    """The item's evidence key, stable for comparing across chats."""
    key = (item.get("proof") or {}).get("fact_key", {})
    return json.dumps(key, sort_keys=True, separators=(",", ":"))


def load_context(session: Session, chat_id: int) -> ChatContext:
    """The chat's context, or an empty one for old chats without any."""
    chat = session.get(Chat, chat_id)
    try:
        return ChatContext.model_validate((chat.context if chat else None) or {})
    except ValidationError:
        return ChatContext()


def save_context(session: Session, chat_id: int, context: ChatContext) -> None:
    """Store the context on the chat row (the caller commits)."""
    chat = session.get(Chat, chat_id)
    if chat is not None:
        chat.context = context.model_dump()


def _period_view(period: Any) -> dict:
    if isinstance(period, dict):
        return {
            "label": str(period.get("label", "")),
            "expression": period.get("expression", ""),
            "start": str(period.get("start", "")),
            "end": str(period.get("end", "")),
            "text": str(period.get("text", "")),
        }
    expression = getattr(period, "expression", "")
    if hasattr(expression, "model_dump"):
        expression = expression.model_dump()
    return {
        "label": str(getattr(period, "label", "")),
        "expression": expression,
        "start": str(getattr(period, "start", "")),
        "end": str(getattr(period, "end", "")),
        "text": str(getattr(period, "text", "")),
    }


def _draft_table(block: dict) -> str | None:
    """The notebook table the draft block used (rendered blocks lose it)."""
    return (block.get("table") or {}).get("table") or (block.get("chart") or {}).get("table")


def _table_items(
    block: dict, table: str | None, items: dict[str, dict]
) -> tuple[str | None, list[str]]:
    """The dimension and first-column values of one shown list."""
    rows = block.get("rows") or []
    if block.get("type") == "chart":
        data = block.get("data") or {}
        rows = data.get("rows") or []
    names: list[str] = []
    for row in rows[:50]:
        if isinstance(row, list) and row:
            names.append(str(row[0]))
        elif isinstance(row, dict) and row:
            first = next(iter(row.values()), None)
            if isinstance(first, dict):
                names.append(str(first.get("f", first.get("v", ""))))
            elif first is not None:
                names.append(str(first))
    dimension = None
    if table and table in items:
        split_by = (items[table].get("proof") or {}).get("split_by") or []
        dimension = split_by[0] if split_by else None
    return dimension, names


def update_context(context: ChatContext, finished: FinishedAnswer) -> ChatContext:
    """Fold one done answer into the chat memory (pure: no database)."""
    items = {item.get("label"): item for item in finished.items if item.get("label")}
    values = {label: "" for label in finished.used_labels}
    try:
        from charie.chat.analyst.notebook import NotebookItem

        parsed = [NotebookItem.model_validate(item) for item in finished.items]
        values = values_for(parsed, finished.style)
    except (ValidationError, ValueError):
        pass
    focus = Focus(
        message_id=finished.message_id,
        question=finished.question,
        kind=finished.kind,
        asks=list(finished.asks),
        filters=list(finished.filters),
        periods=[_period_view(period) for period in finished.periods],
    )
    lists = list(context.lists)
    shown = [block for block in finished.blocks if block.get("type") in ("table", "chart")]
    used = [
        block
        for block in (finished.draft.get("blocks") or [])
        if block.get("type") in ("table", "chart")
    ]
    for pos, block in enumerate(shown):
        table = _draft_table(used[pos]) if pos < len(used) else None
        dimension, names = _table_items(block, table, items)
        lists.append(
            ShownList(
                message_id=finished.message_id,
                title=str(block.get("title", "")),
                dimension=dimension,
                items=names[:50],
            )
        )
    lists = lists[-3:]
    said = list(context.said)
    # A rerun without proof keeps the newest same-label key.
    old_keys = {fact.ref.split(":", 1)[-1]: fact.key for fact in said}
    for label in finished.used_labels:
        item = items.get(label)
        if item is None or item.get("kind") != "number":
            continue
        ref = f"{finished.message_id}:{label}"
        value = item.get("value") or {}
        key = fact_key_text(item)
        if key == "{}" and label in old_keys:
            key = old_keys[label]
        said = [fact for fact in said if fact.ref != ref]
        said.append(
            SaidFact(
                ref=ref,
                key=key,
                description=str(item.get("description", "")),
                text=str(values.get(label, "")),
                value=str(value.get("value", "")),
                unit=str(value.get("unit", "")),
                currency=str(value.get("currency", "")),
                data_through=finished.data_through,
                kb_version=finished.kb_version,
            )
        )
    said = said[-60:]
    reasons: list[OpenReason] = []
    for block in finished.draft.get("blocks") or []:
        if block.get("type") != "text":
            continue
        for sentence in block.get("sentences") or []:
            if sentence.get("kind") != "possible_reason":
                continue
            reasons.append(
                OpenReason(
                    message_id=finished.message_id,
                    text=fill_labels(str(sentence.get("text", "")), values),
                    labels=list(sentence.get("proof") or []),
                )
            )
    open_reasons = reasons if reasons else list(context.open_reasons)
    return ChatContext(
        focus=focus,
        lists=lists,
        said=said,
        open_reasons=open_reasons,
        pending_choice=context.pending_choice,
    )
