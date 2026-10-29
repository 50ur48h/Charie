"""Settings read from `.env` (one field per name in architecture 07).

Every field is optional, so the apps start for health checks and tests.
Secrets stay as `SecretStr`; never print or log `Settings` as a whole.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """A needed setting is missing."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = None
    practice_db_url: str | None = None
    charie_password: SecretStr | None = None
    charie_secret_key: SecretStr | None = None
    charie_encryption_key: SecretStr | None = None
    charie_chat_url: str = "http://localhost:5173"
    charie_learner_url: str = "http://localhost:5174"
    meta_api_key: SecretStr | None = None
    meta_api_base_url: str = "https://api.meta.ai/v1"
    azure_di_endpoint: str | None = None
    azure_di_key: SecretStr | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_key: SecretStr | None = None
    azure_openai_embedding_deployment: str | None = None
    azure_openai_api_version: str | None = None
    ai_replay: Literal["off", "record", "replay"] = "off"
    ai_replay_dir: str = "backend/tests/replays/"
    app_env: Literal["local", "azure"] = "local"


@lru_cache
def get_settings() -> Settings:
    """The cached settings. Tests that change the environment clear the cache."""
    return Settings()


def require_env(name: str) -> str:
    """Return a needed setting, or say where to put it (never the value)."""
    value = getattr(get_settings(), name.lower(), None)
    if value is None:
        raise ConfigError(
            f"{name} is missing. Add it to .env on the laptop, or to the app's secrets on Azure."
        )
    return value.get_secret_value() if isinstance(value, SecretStr) else value
