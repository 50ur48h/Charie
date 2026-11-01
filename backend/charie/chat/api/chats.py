"""Chat addresses: list, create, rename, delete, open, ask (P10.1)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from charie.chat import chat_store
from charie.chat.analyst.runner import start
from charie.shared.db import get_session

chats_router = APIRouter()


class CreateChatBody(BaseModel):
    title: str | None = None


class RenameBody(BaseModel):
    title: str


class AskBody(BaseModel):
    text: str
    mode: str = "thinking"
    choice: dict | None = None


def _chat_shape(session: Session, chat) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }


@chats_router.get("/api/chats")
def list_chats(session: Session = Depends(get_session)) -> dict:
    """Every chat, newest first."""
    return {"chats": [_chat_shape(session, chat) for chat in chat_store.list_chats(session)]}


@chats_router.post("/api/chats", status_code=201)
def create_chat(
    body: CreateChatBody | None = None, session: Session = Depends(get_session)
) -> dict:
    """A new chat. A title can wait for the first question."""
    chat = chat_store.create_chat(session)
    session.commit()
    if body is not None and body.title is not None:
        chat_store.rename_chat(session, chat.id, body.title)
        session.commit()
    return _chat_shape(session, chat)


@chats_router.get("/api/chats/{chat_id}")
def open_chat(chat_id: int, session: Session = Depends(get_session)) -> dict:
    """The chat plus its messages, oldest first."""
    return chat_store.open_chat(session, chat_id)


@chats_router.patch("/api/chats/{chat_id}")
def rename_chat(chat_id: int, body: RenameBody, session: Session = Depends(get_session)) -> dict:
    """Rename a chat."""
    chat = chat_store.rename_chat(session, chat_id, body.title)
    session.commit()
    return _chat_shape(session, chat)


@chats_router.delete("/api/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: int, session: Session = Depends(get_session)) -> None:
    """Delete a chat. A running question refuses first."""
    chat_store.delete_chat(session, chat_id)
    session.commit()
    return None


@chats_router.post("/api/chats/{chat_id}/messages", status_code=201)
async def ask(chat_id: int, body: AskBody, session: Session = Depends(get_session)) -> dict:
    """Ask a question. Returns at once; the answer runs in the background."""
    async with chat_store.chat_lock(chat_id):
        user_message, assistant_message = chat_store.ask_question(
            session, chat_id, body.text, body.mode, body.choice
        )
        session.commit()
        user_id, assistant_id = user_message.id, assistant_message.id
    start(assistant_id)
    return {"user_message_id": user_id, "assistant_message_id": assistant_id}
