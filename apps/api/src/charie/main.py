"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from charie import health
from charie.catalog import routes as catalog_routes
from charie.config import Settings, get_settings
from charie.datasources import routes as datasource_routes
from charie.invitations import routes as invitation_routes
from charie.knowledge import routes as knowledge_routes
from charie.orgs import routes as orgs_routes
from charie.runs import routes as runs_routes
from charie.semantic import routes as semantic_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Reconcile runs a restart stopped, then serve."""
    from charie.agent.scheduler import sweep_orphaned_runs

    try:
        await sweep_orphaned_runs()
    except Exception:
        logger.exception("could not reconcile interrupted runs at startup")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application."""
    resolved = settings if settings is not None else get_settings()

    # Before anything is mounted: a process that boots and then fails open is indistinguishable...
    resolved.assert_auth_is_production_safe()
    resolved.assert_secrets_backend_is_production_safe()
    # WP11.2b. The third of these, and the same shape as the first two.
    resolved.assert_llm_providers_are_production_safe()

    app = FastAPI(
        title="Charie API",
        version=health.resolve_version(),
        lifespan=_lifespan,
    )

    if settings is not None:
        # Routes read settings through the dependency.
        app.dependency_overrides[get_settings] = lambda: resolved

    # The web app is the only first-party client (arch 7.2 — no APIM in V1).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Settings, not a validator.
    app.state.settings = resolved
    app.state.token_validator = None

    app.include_router(health.router)
    app.include_router(orgs_routes.router)
    app.include_router(invitation_routes.router)
    app.include_router(datasource_routes.router)
    app.include_router(catalog_routes.router)
    app.include_router(knowledge_routes.router)
    app.include_router(runs_routes.router)
    app.include_router(semantic_routes.router)

    if resolved.auth_mode == "dev":
        # Imported here, not at module scope: the prod image does not contain this module at all.
        from charie.auth import dev_issuer

        app.state.dev_issuer = dev_issuer.build_dev_issuer(resolved)
        app.include_router(dev_issuer.router)

    return app


app = create_app()
