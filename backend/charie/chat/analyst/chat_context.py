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
    """One number the owner saw, in the words it was shown in."""

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


class ChatContext(BaseModel):
    """The whole chat memory; every field has a default, so old chats load."""

    focus: Focus | None = None
    lists: list[ShownList] = Field(default=[])
    said: list[SaidFact] = Field(default=[])
    open_reasons: list[OpenReason] = Field(default=[])


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
    old_keys = {fact.ref: fact.key for fact in said}
    for label in finished.used_labels:
        item = items.get(label)
        if item is None or item.get("kind") != "number":
            continue
        value = item.get("value") or {}
        key = fact_key_text(item)
        if key == "{}" and label in old_keys:
            key = old_keys[label]
        said = [fact for fact in said if fact.ref != label]
        said.append(
            SaidFact(
                ref=label,
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
    return ChatContext(focus=focus, lists=lists, said=said, open_reasons=open_reasons)
