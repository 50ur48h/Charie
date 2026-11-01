"""The owner's memories: list, forget one, forget everything (P11.5)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.tables.chat import Chat, Memory
from charie.shared.text.numbers import MONTHS

memories_router = APIRouter()


def _source_date(created_at) -> str:
    """'12 Oct' for a datetime, like the Calm Settings design."""
    if created_at is None:
        return ""
    day = created_at.day if hasattr(created_at, "day") else 0
    month = created_at.month if hasattr(created_at, "month") else 0
    if not day or not 1 <= month <= 12:
        return ""
    return f"{day} {MONTHS[month - 1]}"


def _source(memory: Memory, session) -> str:
    """'From the chat "<title>" · 12 Oct', or the deleted-chat words."""
    date = _source_date(memory.created_at)
    tail = f" · {date}" if date else ""
    if memory.source_chat_id is None:
        return f"From a deleted chat{tail}"
    chat = session.get(Chat, memory.source_chat_id)
    if chat is None:
        return f"From a deleted chat{tail}"
    return f'From the chat "{chat.title}"{tail}'


def _saved_at(memory: Memory) -> str:
    created = memory.created_at
    if created is None:
        return ""
    if hasattr(created, "isoformat"):
        return created.isoformat()
    return str(created)


@memories_router.get("/api/memories")
def list_memories(session=Depends(get_session)) -> list[dict]:
    """Every active memory, newest first."""
    rows = session.scalars(
        select(Memory).where(Memory.active.is_(True)).order_by(Memory.id.desc())
    ).all()
    return [
        {
            "id": row.id,
            "text": row.text_,
            "source": _source(row, session),
            "saved_at": _saved_at(row),
        }
        for row in rows
    ]


@memories_router.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, session=Depends(get_session)):
    """Forget one memory; 404 when it isn't there."""
    row = session.get(Memory, memory_id)
    if row is None or not row.active:
        raise ApiError(404, "not_found", "That memory isn't there any more.")
    row.active = False
    session.commit()
    return {"ok": True}


@memories_router.delete("/api/memories")
def clear_memories(session=Depends(get_session)):
    """Forget every active memory."""
    rows = session.scalars(select(Memory).where(Memory.active.is_(True))).all()
    for row in rows:
        row.active = False
    session.commit()
    return {"ok": True}
