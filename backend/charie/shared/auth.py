"""Real login: one shared password, a signed cookie, and guards.

The session cookie holds only `logged_in_at` (Unix seconds). Anything else
the screens need comes from `/api/me` and `/api/settings`.
"""

import hmac
import time
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from charie.shared.config import get_settings, require_env
from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.settings import get_setting, set_setting

SESSION_COOKIE = "charie_session"
SESSION_DAYS = 7
SESSION_TTL = SESSION_DAYS * 24 * 60 * 60
TRIES_WINDOW = 5 * 60
TRIES_LIMIT = 5

_phasher = PasswordHasher()


def now() -> float:
    """Unix seconds. Tests move it to age sessions and tries."""
    return time.time()


class LoginBody(BaseModel):
    password: str


class PasswordBody(BaseModel):
    current: str
    new: str


class OkResponse(BaseModel):
    ok: bool


class MeResponse(BaseModel):
    logged_in: bool
    setup_done: bool
    theme: str
    chat_url: str
    learner_url: str


def password_configured(session: Session) -> bool:
    """A hash is saved, or the `CHARIE_PASSWORD` secret exists."""
    if get_setting(session, "password_hash"):
        return True
    return get_settings().charie_password is not None


def check_password(session: Session, password: str) -> bool:
    """True when the password matches. Raises 503 when none is set up."""
    saved = get_setting(session, "password_hash")
    if saved:
        try:
            return _phasher.verify(saved, password)
        except VerifyMismatchError:
            return False
    secret = get_settings().charie_password
    if secret is None:
        raise ApiError(
            503,
            "no_password",
            "No password is set up yet. Add CHARIE_PASSWORD to .env, then restart.",
        )
    return hmac.compare_digest(password, secret.get_secret_value())


class LoginLimiter:
    """Too many wrong tries from one address blocks it for 5 minutes."""

    def __init__(self) -> None:
        self.tries: dict[str, list[float]] = {}

    def _recent(self, address: str, at: float) -> list[float]:
        kept = [hit for hit in self.tries.get(address, []) if at - hit < TRIES_WINDOW]
        self.tries[address] = kept
        return kept

    def blocked(self, address: str, at: float | None = None) -> bool:
        return len(self._recent(address, at if at is not None else now())) >= TRIES_LIMIT

    def record(self, address: str, at: float | None = None) -> None:
        moment = at if at is not None else now()
        self._recent(address, moment).append(moment)

    def clear(self, address: str) -> None:
        self.tries.pop(address, None)


limiter = LoginLimiter()


def address_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def require_login(request: Request) -> None:
    """Refuse without a fresh login stamp. Only the cookie is read."""
    stamped = request.session.get("logged_in_at")
    if not isinstance(stamped, (int, float)) or now() - stamped >= SESSION_TTL:
        raise ApiError(401, "login_needed", "Please sign in first.")


def _too_many() -> ApiError:
    return ApiError(
        429,
        "too_many_tries",
        "Too many wrong passwords. Please wait 5 minutes, then try again.",
    )


login_router = APIRouter()


@login_router.post("/api/login", response_model=OkResponse)
def login(body: LoginBody, request: Request, session: Session = Depends(get_session)) -> OkResponse:
    address = address_of(request)
    if limiter.blocked(address):
        raise _too_many()
    if not check_password(session, body.password):
        limiter.record(address)
        raise ApiError(401, "wrong_password", "That password didn't work. Try again.")
    limiter.clear(address)
    request.session["logged_in_at"] = now()
    return OkResponse(ok=True)


auth_router = APIRouter()


@auth_router.post("/api/logout", response_model=OkResponse)
def logout(request: Request) -> OkResponse:
    request.session.clear()
    return OkResponse(ok=True)


@auth_router.get("/api/me", response_model=MeResponse)
def me(session: Session = Depends(get_session)) -> MeResponse:
    settings = get_settings()
    return MeResponse(
        logged_in=True,
        setup_done=get_setting(session, "setup_done"),
        theme=get_setting(session, "theme"),
        chat_url=settings.charie_chat_url,
        learner_url=settings.charie_learner_url,
    )


@auth_router.post("/api/password")
def change_password(
    body: PasswordBody, request: Request, session: Session = Depends(get_session)
) -> OkResponse:
    address = address_of(request)
    if limiter.blocked(address):
        raise _too_many()
    if not password_configured(session):
        raise ApiError(
            503,
            "no_password",
            "No password is set up yet. Add CHARIE_PASSWORD to .env, then restart.",
        )
    saved = get_setting(session, "password_hash")
    if saved:
        try:
            current_ok = _phasher.verify(saved, body.current)
        except VerifyMismatchError:
            current_ok = False
    else:
        secret = get_settings().charie_password
        current_ok = secret is not None and hmac.compare_digest(
            body.current, secret.get_secret_value()
        )
    if not current_ok:
        limiter.record(address)
        raise ApiError(400, "wrong_password", "The current password isn't right.")
    if len(body.new) < 8:
        raise ApiError(400, "password_too_short", "The new password needs at least 8 characters.")
    set_setting(session, "password_hash", _phasher.hash(body.new))
    limiter.clear(address)
    return OkResponse(ok=True)


class OriginAndJsonCheck(BaseHTTPMiddleware):
    """Changes must come from our own screens, as JSON.

    The one exception is document upload: `POST /api/documents` carries
    the file as multipart, so the JSON check is skipped there — but the
    same-origin check still applies.
    """

    CHANGE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith("/api/") and request.method in self.CHANGE_METHODS:
            if not self._same_origin(request):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "bad_origin",
                        "message": (
                            "This change didn't come from Charie's own screens, so it was refused."
                        ),
                    },
                )
            if (
                self._has_body(request)
                and not self._is_json(request)
                and not self._is_upload(request)
            ):
                return JSONResponse(
                    status_code=415,
                    content={
                        "error": "json_only",
                        "message": "Please send the details as JSON.",
                    },
                )
        return await call_next(request)

    def _same_origin(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if not origin:
            return False
        try:
            wanted = urlsplit(origin)
        except ValueError:
            return False
        host = request.headers.get("host", "")
        return (wanted.hostname or "") == host.split(":")[0] and wanted.port == _port_of(host)

    @staticmethod
    def _has_body(request: Request) -> bool:
        if request.headers.get("transfer-encoding"):
            return True
        try:
            return int(request.headers.get("content-length", "0")) > 0
        except ValueError:
            return True

    @staticmethod
    def _is_json(request: Request) -> bool:
        content_type = request.headers.get("content-type", "")
        return content_type.split(";")[0].strip().lower() == "application/json"

    @staticmethod
    def _is_upload(request: Request) -> bool:
        """The multipart exception: one file upload, same origin still required."""
        if request.url.path != "/api/documents" or request.method != "POST":
            return False
        content_type = request.headers.get("content-type", "")
        return content_type.split(";")[0].strip().lower().startswith("multipart/")


def _port_of(host: str) -> int | None:
    if ":" in host:
        try:
            return int(host.rsplit(":", 1)[1])
        except ValueError:
            return None
    return None


def session_middleware_kwargs() -> dict:
    return {
        "secret_key": require_env("CHARIE_SECRET_KEY"),
        "session_cookie": SESSION_COOKIE,
        "max_age": SESSION_TTL,
        "same_site": "lax",
        "https_only": get_settings().app_env == "azure",
    }
