"""The learner API."""

from fastapi import FastAPI

from charie.learner.api.learning import learning_router
from charie.learner.api.setup import setup_router
from charie.learner.api.sources import sources_router
from charie.shared.auth import auth_router, login_router
from charie.shared.settings import settings_router
from charie.shared.status import status_router
from charie.shared.web import create_app


def build_app() -> FastAPI:
    """One learner app (tests build their own on a throwaway database)."""
    return create_app(
        "learner",
        routers=(
            auth_router,
            settings_router,
            sources_router,
            setup_router,
            learning_router,
            status_router,
        ),
        public_routers=(login_router,),
    )


app = build_app()
