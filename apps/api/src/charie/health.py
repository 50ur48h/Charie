"""Liveness probe."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from charie import __version__
from charie.config import Settings, get_settings
from charie.llm.registry import unresolvable_roles

router = APIRouter(tags=["meta"])


class HealthResponse(BaseModel):
    """Payload of ``GET /healthz``.

    Carries no configuration, no environment name and no secret.
    """

    status: Literal["ok", "degraded"] = "ok"
    version: str = Field(description="Application version from package metadata.")
    git_sha: str = Field(description="Commit the image was built from, or 'unknown'.")
    missing_settings: list[str] = Field(
        default_factory=list,
        description=(
            "Environment variables this configuration requires and does not have. "
            "Names only — never values. Empty when status is 'ok'."
        ),
    )
    unservable_roles: list[str] = Field(
        default_factory=list,
        description=(
            "Model roles this configuration cannot serve, and why. A deployment "
            "can satisfy every required variable and still map a role to a tier "
            "no model fills, which fails at the first question rather than here. "
            "Names and reasons only — never a credential. Empty when 'ok'."
        ),
    )


def resolve_version() -> str:
    """Installed package version, falling back to the source constant."""
    try:
        return package_version("charie")
    except PackageNotFoundError:
        return __version__


@router.get("/healthz", summary="Liveness probe")
async def healthz(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Whether this deployment can do its job, not merely whether it is running."""
    missing = settings.missing_for_mode()
    # Only worth asking once the variables are there: with `LLM_MODELS` unset.
    unservable = [] if missing else unresolvable_roles(settings)
    return HealthResponse(
        status="degraded" if (missing or unservable) else "ok",
        version=resolve_version(),
        git_sha=settings.git_sha,
        missing_settings=missing,
        unservable_roles=unservable,
    )
