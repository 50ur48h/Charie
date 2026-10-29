"""Every error is JSON `{ "error", "message" }`, in plain English."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """A known failure with its status, code and plain message."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def install_error_handlers(app: FastAPI) -> None:
    """Turn every failure into the one error shape."""

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status,
            content={"error": error.code, "message": error.message},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=error.status_code,
                content={"error": "not_found", "message": "That address doesn't exist."},
            )
        raise error

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, error: RequestValidationError) -> JSONResponse:
        fields = sorted({str(part) for item in error.errors() for part in item["loc"][1:]})
        names = ", ".join(fields) if fields else "the details"
        return JSONResponse(
            status_code=400,
            content={
                "error": "bad_request",
                "message": f"Some details are missing or not valid: `{names}`.",
            },
        )

    @app.exception_handler(Exception)
    async def crash(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": "server_error",
                "message": "Something went wrong on our side. Please try again.",
            },
        )
