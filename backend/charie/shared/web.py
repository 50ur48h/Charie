"""The shared app builder: health, errors and the built screens."""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, JSONResponse

from charie.shared.errors import install_error_handlers
from charie.shared.logs import setup_logging

REPO = Path(__file__).resolve().parents[3]
LONG_CACHE = "public, max-age=31536000, immutable"


def health_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    return router


def create_app(
    app_name: str, routers: tuple[APIRouter, ...] = (), static_dir: Path | None = None
) -> FastAPI:
    """One app: logging, the error shape, `/api/health`, then the screens."""
    setup_logging()
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(health_router())
    for router in routers:
        app.include_router(router)

    screens = static_dir or REPO / "frontend" / app_name / "dist"

    @app.get("/{path:path}", response_model=None)
    async def pages(path: str):
        if path == "api" or path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"error": "not_found", "message": "That address doesn't exist."},
            )
        wanted = (screens / path).resolve()
        if path and wanted.is_relative_to(screens) and wanted.is_file():
            headers = {"Cache-Control": LONG_CACHE} if path.startswith("assets/") else None
            return FileResponse(wanted, headers=headers)
        index = screens / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse(
            status_code=404,
            content={
                "error": "screens_not_built",
                "message": "The screens aren't built yet. Run npm run build in frontend/.",
            },
        )

    return app
