"""The settings in our database: defaults, read, write, and the API.

Every key and default comes from architecture 05. `password_hash` never
leaves the server; `time_zone` is empty until the setup guide sets it.
"""

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.tables.settings import Setting

DEFAULTS: dict[str, Any] = {
    "password_hash": "",
    "theme": "sage",
    "answer_length": "normal",
    "number_format": "short",
    "thinking_minutes": 10,
    "show_reading": True,
    "memory_on": True,
    "spend_limit_usd": 150,
    "spend_warn_percent": 80,
    "time_zone": None,
    "self_test_question_count": 50,
    "strict_mode": False,
    "setup_done": False,
}

# What `GET /api/settings` shows, in order. Never `password_hash`.
PUBLIC_KEYS = (
    "theme",
    "answer_length",
    "number_format",
    "thinking_minutes",
    "show_reading",
    "memory_on",
    "spend_limit_usd",
    "spend_warn_percent",
    "time_zone",
    "strict_mode",
    "setup_done",
)


def get_setting(session: Session, key: str) -> Any:
    """The saved value, or the default when nothing is saved."""
    row = session.get(Setting, key)
    if row is None:
        return DEFAULTS[key]
    return row.value


def set_setting(session: Session, key: str, value: Any) -> None:
    """Save one setting (the caller validates first)."""
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    session.commit()


def read_settings(session: Session) -> dict[str, Any]:
    """Every public setting, with defaults filled in."""
    return {key: get_setting(session, key) for key in PUBLIC_KEYS}


def bad_setting(message: str) -> ApiError:
    return ApiError(400, "bad_setting", message)


def check_patch(patch: dict[str, Any]) -> None:
    """Raise `bad_setting` for the first problem, so saves stay all-or-nothing."""
    refused = {"setup_done", "password_hash"}
    for key in patch:
        if key in refused:
            raise bad_setting(f"This setting can't be changed here: `{key}`.")
        if key not in PUBLIC_KEYS:
            raise bad_setting(f"Unknown setting: `{key}`.")
        check_value(key, patch[key])


def check_value(key: str, value: Any) -> None:
    """Raise `bad_setting` unless the value fits the key."""
    if key == "theme":
        if value not in ("sage", "lavender", "mist", "seafoam", "mauve", "slate"):
            raise bad_setting("Theme must be one of: sage, lavender, mist, seafoam, mauve, slate.")
    elif key == "answer_length":
        if value not in ("short", "normal", "detailed"):
            raise bad_setting("Answer length must be short, normal or detailed.")
    elif key == "number_format":
        if value not in ("short", "full"):
            raise bad_setting("Number format must be short or full.")
    elif key == "thinking_minutes":
        if not isinstance(value, int) or isinstance(value, bool) or not 2 <= value <= 15:
            raise bad_setting("Thinking time must be a whole number of minutes from 2 to 15.")
    elif key in ("show_reading", "memory_on", "strict_mode"):
        if not isinstance(value, bool):
            raise bad_setting(f"`{key}` must be true or false.")
    elif key == "spend_limit_usd":
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0.01 <= value <= 100000
        ):
            raise bad_setting("The monthly limit must be between $0.01 and $100,000.")
    elif key == "spend_warn_percent":
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 99:
            raise bad_setting("The warning level must be a whole number from 1 to 99.")
    elif key == "time_zone":
        if value is None:
            return
        if not isinstance(value, str) or not value:
            raise bad_setting(f"Unknown time zone: `{value}`. Use a name like Asia/Kolkata.")
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as err:
            raise bad_setting(
                f"Unknown time zone: `{value}`. Use a name like Asia/Kolkata."
            ) from err


class SettingsPatch(BaseModel):
    model_config = {"extra": "allow"}

    def values(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=False)


settings_router = APIRouter(dependencies=[])


@settings_router.get("/api/settings")
def get_settings(session: Session = Depends(get_session)) -> dict[str, Any]:
    return read_settings(session)


@settings_router.patch("/api/settings")
def patch_settings(patch: SettingsPatch, session: Session = Depends(get_session)) -> dict[str, Any]:
    values = patch.values()
    check_patch(values)
    for key, value in values.items():
        set_setting(session, key, value)
    return read_settings(session)
