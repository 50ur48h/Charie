"""Lasting preferences stated by the owner, saved across chats (P11.5).

Only your own message is read, never the answer. Code checks every
candidate before saving: the length, the numbers and the replaces ids.
A meaning memory also files a learner to-do, so the knowledge can
catch up. Failures never reach the screen.
"""

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.shared.ai.client import get_ai
from charie.shared.knowledge.todos import add_learner_todo
from charie.shared.settings import get_setting
from charie.shared.tables.chat import Chat, Memory, Message

log = logging.getLogger(__name__)

#: A number the AI typed, like 42, $96.2K or 12 Oct.
NUMBER_RE = re.compile(r"\d[\d.,]*")

MemoryKind = Literal["meaning", "focus", "format", "other"]


class ExtractedMemory(BaseModel):
    """One candidate memory in your words."""

    text: str = Field(default="", description="One short first-person sentence.")
    kind: MemoryKind = Field(default="other", description="meaning, focus, format or other.")
    replaces: list[int] = Field(default=[], description="Ids of active memories this replaces.")


class ExtractedMemories(BaseModel):
    """The extraction form: at most 3 candidates."""

    memories: list[ExtractedMemory] = Field(default=[], description="At most 3.")


def normalize_memory_text(text: str) -> str:
    """Compare texts ignoring case, extra spaces and a final full stop."""
    return " ".join((text or "").strip().rstrip(".").split()).lower()


def active_memories(session: Session) -> list[Memory]:
    """Every active memory, oldest first."""
    return list(
        session.scalars(select(Memory).where(Memory.active.is_(True)).order_by(Memory.id)).all()
    )


def memories_for_prompt(session: Session) -> list[str]:
    """Active memory texts, newest first, at most 20."""
    rows = session.scalars(
        select(Memory).where(Memory.active.is_(True)).order_by(Memory.id.desc()).limit(20)
    ).all()
    return [row.text_ for row in rows]


def _checks(candidate: ExtractedMemory, message_text: str, active_ids: set[int]) -> bool:
    """The code checks before saving: length, numbers, replaces ids."""
    text = (candidate.text or "").strip()
    if not 3 <= len(text) <= 200:
        return False
    for raw in NUMBER_RE.findall(text):
        if raw not in message_text:
            return False
    return not any(memory_id not in active_ids for memory_id in candidate.replaces)


def extract_and_save_memories(session: Session, message: Message) -> None:
    """Save lasting preferences from one done user message (or nothing).

    Skips non-user messages, anything not done, and the whole step when
    memory is off. Failures raise to the background caller, which logs.
    """
    if message.role != "user" or message.status != "done":
        return
    if not get_setting(session, "memory_on"):
        return
    active = active_memories(session)
    active_ids = {row.id for row in active}
    known = normalize_memory_text
    seen = {known(row.text_) for row in active}
    result = get_ai().run(
        "extract_memories",
        {
            "message": message.text_,
            "memories": [{"id": row.id, "text": row.text_} for row in active],
        },
        ExtractedMemories,
        app="chat",
        message_id=message.id,
    )
    for candidate in result.memories[:3]:
        if not _checks(candidate, message.text_ or "", active_ids):
            continue
        if known(candidate.text) in seen:
            continue
        row = Memory(
            text_=(candidate.text or "").strip(),
            kind=candidate.kind,
            source_chat_id=message.chat_id,
            active=True,
        )
        session.add(row)
        session.flush()
        seen.add(known(candidate.text))
        for replaced_id in candidate.replaces:
            replaced = session.get(Memory, replaced_id)
            if replaced is not None and replaced.active:
                replaced.active = False
        if candidate.kind == "meaning":
            chat = session.get(Chat, message.chat_id)
            add_learner_todo(
                session,
                "meaning_change",
                f"The user says: {(candidate.text or '').strip()}",
                {
                    "chat_id": message.chat_id,
                    "chat_title": chat.title if chat is not None else "",
                    "message_id": message.id,
                    "words": message.text_,
                },
            )
    session.commit()
