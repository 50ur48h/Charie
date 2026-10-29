"""The chat API."""

from fastapi import FastAPI

from charie.shared.auth import auth_router, login_router
from charie.shared.settings import settings_router
from charie.shared.web import create_app


def build_app() -> FastAPI:
    """One chat app (tests build their own on a throwaway database)."""
    return create_app(
        "chat",
        routers=(auth_router, settings_router),
        public_routers=(login_router,),
    )


app = build_app()
