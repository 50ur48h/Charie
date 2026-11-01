"""Chats on the real database: CRUD, ask, and the runner's context (P10.1)."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.chat.analyst.context import AnalystContext, RunState
from charie.chat.analyst.stream import ThinkingLog
from charie.shared.ai.spending import month_spent, spending_state
from charie.shared.db import session_scope
from charie.shared.errors import ApiError
from charie.shared.knowledge.versions import get_published
from charie.shared.settings import get_setting
from charie.shared.tables.chat import Chat, Message, ThinkingEvent
from charie.shared.tables.sources import DataSource

TITLE_LIMIT = 80
QUESTION_LIMIT = 2000
TITLE_CUT = 60

# One question at a time per chat: the check and the inserts run under
# one asyncio lock per chat, so a double click can't start two questions.
_CHAT_LOCKS: dict[int, asyncio.Lock] = {}


def chat_lock(chat_id: int) -> asyncio.Lock:
    """The lock for one chat, created on first use."""
    lock = _CHAT_LOCKS.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _CHAT_LOCKS[chat_id] = lock
    return lock


def _message_shape(message: Message, thinking: list[dict]) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "text": message.text_,
        "status": message.status,
        "mode": message.mode,
        "answer": message.answer,
        "thinking": thinking,
        "summary": {
            "seconds": message.seconds,
            "steps": message.steps,
            "queries": message.queries,
            "documents": message.documents,
        },
        "cost_usd": float(message.cost_usd or 0),
        "feedback": message.feedback,
        "started_at": message.started_at.isoformat() if message.started_at else None,
        "finished_at": message.finished_at.isoformat() if message.finished_at else None,
    }


def _thinking_lines(session: Session, message_id: int) -> list[dict]:
    rows = session.scalars(
        select(ThinkingEvent)
        .where(ThinkingEvent.message_id == message_id)
        .order_by(ThinkingEvent.seq)
    ).all()
    return [
        {
            "seq": row.seq,
            "kind": row.kind,
            "status": row.status,
            "title": row.title,
            "body": row.body,
            "details": row.details,
        }
        for row in rows
    ]


def create_chat(session: Session) -> Chat:
    """A new chat; the first question names it."""
    chat = Chat(title="New chat")
    session.add(chat)
    session.flush()
    return chat


def list_chats(session: Session) -> list[Chat]:
    """Every chat, newest `updated_at` first."""
    return list(
        session.scalars(select(Chat).order_by(Chat.updated_at.desc(), Chat.id.desc())).all()
    )


def get_chat(session: Session, chat_id: int) -> Chat:
    """One chat, or a 404 that names it."""
    chat = session.get(Chat, chat_id)
    if chat is None:
        raise ApiError(404, "not_found", "That chat doesn't exist any more.")
    return chat


def get_message(session: Session, message_id: int) -> Message:
    """One message, or a 404 that names it."""
    message = session.get(Message, message_id)
    if message is None:
        raise ApiError(404, "not_found", "That message doesn't exist.")
    return message


def open_chat(session: Session, chat_id: int) -> dict:
    """The chat plus its messages, oldest first, thinking in `seq` order."""
    chat = get_chat(session, chat_id)
    messages = session.scalars(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.id)
    ).all()
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
        "messages": [
            _message_shape(message, _thinking_lines(session, message.id)) for message in messages
        ],
    }


def rename_chat(session: Session, chat_id: int, title: str) -> Chat:
    """Rename a chat. A bad title is refused with what a title needs."""
    if not 1 <= len(title) <= TITLE_LIMIT:
        raise ApiError(422, "bad_title", "A chat title needs 1 to 80 characters.")
    chat = get_chat(session, chat_id)
    chat.title = title
    chat.updated_at = datetime.now(UTC)
    session.flush()
    return chat


def chat_is_running(session: Session, chat_id: int) -> bool:
    """A message in this chat is still thinking or writing."""
    return (
        session.scalar(
            select(func.count(Message.id)).where(
                Message.chat_id == chat_id,
                Message.status.in_(("thinking", "writing")),
            )
        )
        > 0
    )


def delete_chat(session: Session, chat_id: int) -> None:
    """Delete the chat row. Foreign keys keep Usage right on their own.

    A running question refuses first: deleting mid-answer would orphan
    the runner's message.
    """
    chat = get_chat(session, chat_id)
    if chat_is_running(session, chat_id):
        raise ApiError(
            409,
            "question_running",
            "Charie is still working on a question in this chat. "
            "Wait for it to finish, or click Finish now.",
        )
    session.delete(chat)
    session.flush()


def _cut_title(question: str) -> str:
    """The question cut to 60 characters at a word boundary, with … if cut."""
    if len(question) <= TITLE_CUT:
        return question
    cut = question[:TITLE_CUT].rsplit(" ", 1)[0]
    return (cut or question[:TITLE_CUT]) + "…"


def _published_version_id(session: Session) -> int:
    published = get_published(session)
    if published is None:
        raise ApiError(
            409, "not_ready", "Charie is still learning. Finish the setup in the Learner first."
        )
    return published.id


def _data_through(session: Session):
    row = session.scalar(select(DataSource).order_by(DataSource.id.desc()).limit(1))
    return row.data_through if row is not None else None


def _check_spending(session: Session) -> None:
    spent = month_spent(session, datetime.now(UTC))
    limit = get_setting(session, "spend_limit_usd")
    warn = get_setting(session, "spend_warn_percent")
    if spending_state(spent, limit, warn) == "paused":
        raise ApiError(
            409,
            "spending_paused",
            "New AI work is paused because this month's spending limit is reached. "
            "Raise the limit on the Usage page to continue.",
        )


def ask_question(
    session: Session, chat_id: int, text: str, mode: str, choice: dict | None = None
) -> tuple[Message, Message]:
    """Save the user's question and its thinking assistant message.

    Checks run in the plan's order: text, mode, no running question,
    spending, a published version. `choice` is accepted and ignored
    until P11.3. Call under `chat_lock(chat_id)`.
    """
    _ = choice
    question = text.strip()
    if not question:
        raise ApiError(422, "empty_question", "Please type a question.")
    if len(text) > QUESTION_LIMIT:
        raise ApiError(422, "question_too_long", "Questions can be up to 2,000 characters.")
    if mode != "thinking":
        raise ApiError(
            422, "quick_not_ready", "Quick mode is coming. Please use thinking mode for now."
        )
    chat = get_chat(session, chat_id)
    if chat_is_running(session, chat_id):
        raise ApiError(
            409,
            "question_running",
            "Charie is still working on a question in this chat. "
            "Wait for it to finish, or click Finish now.",
        )
    _check_spending(session)
    version_id = _published_version_id(session)
    now = datetime.now(UTC)
    user_message = Message(
        chat_id=chat.id,
        role="user",
        text_=question,
        status="done",
        started_at=now,
        finished_at=now,
    )
    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        mode="thinking",
        kb_version_id=version_id,
        data_through=_data_through(session),
        started_at=now,
    )
    session.add(user_message)
    session.add(assistant_message)
    session.flush()
    if chat.title == "New chat":
        chat.title = _cut_title(question)
    chat.updated_at = now
    session.flush()
    return user_message, assistant_message


def build_context(message_id: int) -> AnalystContext | None:
    """The runner's context for one assistant message, or None when gone."""
    with session_scope() as session:
        message = session.get(Message, message_id)
        if message is None or message.role != "assistant":
            return None
        question_row = session.scalar(
            select(Message)
            .where(Message.chat_id == message.chat_id, Message.role == "user")
            .order_by(Message.id.desc())
            .limit(1)
        )
        settings = {
            "thinking_minutes": get_setting(session, "thinking_minutes"),
            "answer_length": get_setting(session, "answer_length"),
            "number_format": get_setting(session, "number_format"),
        }
        return AnalystContext(
            message_id=message.id,
            chat_id=message.chat_id,
            question=question_row.text_ if question_row is not None else "",
            kb_version_id=message.kb_version_id or 0,
            data_through=message.data_through,
            settings=settings,
            log=ThinkingLog(message.id),
            state=RunState(),
            private=False,
        )


def mark_failed(message_id: int, body: str) -> None:
    """A crashed question: failed, with a failed note line, stamped."""
    with session_scope() as session:
        message = session.get(Message, message_id)
        if message is None:
            return
        ThinkingLog(message_id).add("note", "Answering failed", body, status="failed")
        message.status = "failed"
        message.finished_at = datetime.now(UTC)
        session.commit()


def mark_stopped(session: Session, message: Message, body: str) -> None:
    """A question the restart cut off: stopped, with a failed note line."""
    top = session.scalar(
        select(func.max(ThinkingEvent.seq)).where(ThinkingEvent.message_id == message.id)
    )
    session.add(
        ThinkingEvent(
            message_id=message.id,
            seq=(top or 0) + 1,
            kind="note",
            status="failed",
            title="Stopped",
            body=body,
            details={},
        )
    )
    message.status = "stopped"
    message.finished_at = datetime.now(UTC)
    session.flush()
