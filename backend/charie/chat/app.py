"""The chat API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from charie.chat import chat_store
from charie.chat.api.chats import chats_router
from charie.chat.api.memories import memories_router
from charie.chat.api.messages import messages_router
from charie.chat.api.suggest import suggest_router
from charie.chat.api.usage import usage_router
from charie.shared.auth import auth_router, login_router
from charie.shared.db import session_scope
from charie.shared.knowledge.routes import make_knowledge_router
from charie.shared.questions_api import questions_router
from charie.shared.settings import settings_router
from charie.shared.status import status_router
from charie.shared.tables.chat import Message
from charie.shared.web import create_app

STOPPED_BODY = "Stopped: the app restarted while I was working. Please ask again."


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Mark cut-off questions stopped. The notebook is kept."""
    with session_scope() as session:
        rows = session.scalars(
            select(Message).where(Message.status.in_(("thinking", "writing")))
        ).all()
        for message in rows:
            chat_store.mark_stopped(session, message, STOPPED_BODY)
        session.commit()
    yield


def build_app() -> FastAPI:
    """One chat app (tests build their own on a throwaway database)."""
    return create_app(
        "chat",
        routers=(
            auth_router,
            settings_router,
            status_router,
            usage_router,
            questions_router,
            chats_router,
            memories_router,
            messages_router,
            suggest_router,
            make_knowledge_router(allow_draft=False),
        ),
        public_routers=(login_router,),
        lifespan=lifespan,
    )


app = build_app()
