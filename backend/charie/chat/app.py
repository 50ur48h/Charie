"""The chat API."""

from fastapi import FastAPI

from charie.chat.api.usage import usage_router
from charie.shared.auth import auth_router, login_router
from charie.shared.knowledge.routes import make_knowledge_router
from charie.shared.questions_api import questions_router
from charie.shared.settings import settings_router
from charie.shared.status import status_router
from charie.shared.web import create_app


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
            make_knowledge_router(allow_draft=False),
        ),
        public_routers=(login_router,),
    )


app = build_app()
