"""The chat app's AI forms, and naming a chat after its first answer."""

import threading

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from charie.shared.ai.client import get_ai
from charie.shared.tables.chat import Message


class ChatTitle(BaseModel):
    """Form for the name_chat job. Titles label a chat; labels are text."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(description="A short title for the chat, 2 to 6 words, no digits.")


#: A slow or failed naming keeps the automatic title; never retry.
TITLE_TIMEOUT_SECONDS = 10


def _title_ok(title: str) -> bool:
    """P05.8's rules plus one line, 60 characters, no final full stop."""
    text = (title or "").strip()
    if not 2 <= len(text.split()) <= 6:
        return False
    if "\n" in text or len(text) > 60 or text.endswith("."):
        return False
    if any(char.isdigit() for char in text):
        return False
    return '"' not in text and "'" not in text


def _first_question(session, chat_id: int) -> str:
    """The chat's first user message, the automatic title's source."""
    row = session.scalar(
        select(Message)
        .where(Message.chat_id == chat_id, Message.role == "user")
        .order_by(Message.id)
    )
    return row.text_ if row is not None else ""


def _reading_text(answer) -> str:
    """The saved reading block, the title's second input when shown."""
    if not isinstance(answer, dict):
        return ""
    for block in answer.get("blocks") or []:
        if isinstance(block, dict) and block.get("type") == "reading" and block.get("text"):
            return str(block["text"])
    return ""


def _ask_title(topic: str, message_id: int) -> str | None:
    """The AI's title, or None on failure or timeout (no retry)."""
    outcome: dict = {}

    def _call() -> None:
        try:
            outcome["title"] = (
                get_ai()
                .run(
                    "name_chat",
                    {"topic": topic},
                    ChatTitle,
                    app="chat",
                    message_id=message_id,
                )
                .title
            )
        except Exception:
            outcome["title"] = None

    worker = threading.Thread(target=_call, daemon=True)
    worker.start()
    worker.join(TITLE_TIMEOUT_SECONDS)
    if worker.is_alive():
        return None
    title = outcome.get("title")
    return title if isinstance(title, str) else None


def name_chat_if_new(session, chat, message) -> None:
    """Name a chat after its first done answer; never touch a chosen title."""
    from charie.chat.chat_store import _cut_title

    first = _first_question(session, chat.id)
    if not first or (chat.title or "") != _cut_title(first):
        return
    reading = _reading_text(message.answer)
    topic = f"{first}\n{reading}" if reading else first
    title = _ask_title(topic, message.id)
    if title is None or not _title_ok(title):
        return
    chat.title = title.strip()
    session.commit()
