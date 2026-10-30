"""The learner API."""

from fastapi import FastAPI

from charie.learner.api.knowledge import knowledge_router
from charie.learner.api.learning import learning_router
from charie.learner.api.owner_notes import owner_notes_router
from charie.learner.api.setup import setup_router
from charie.learner.api.sources import sources_router
from charie.shared.auth import auth_router, login_router
from charie.shared.knowledge.routes import make_knowledge_router
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
            knowledge_router,
            make_knowledge_router(allow_draft=True),
            setup_router,
            learning_router,
            owner_notes_router,
            status_router,
        ),
        public_routers=(login_router,),
    )


app = build_app()
