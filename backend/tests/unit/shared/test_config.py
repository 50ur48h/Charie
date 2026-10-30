import pytest
from pydantic import ValidationError

from charie.shared.config import ConfigError, Settings, get_settings, require_env


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch):
    monkeypatch.delenv("AI_REPLAY", raising=False)
    monkeypatch.delenv("CHARIE_PASSWORD", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_reads_env_names(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("CHARIE_PASSWORD", "secret-word")
    settings = get_settings()
    assert settings.database_url == "postgresql://x"
    assert settings.charie_password is not None
    assert settings.charie_password.get_secret_value() == "secret-word"
    assert settings.meta_api_base_url == "https://api.meta.ai/v1"
    assert settings.ai_replay == "off"
    assert settings.app_env == "local"


def test_replay_mode_must_be_known(monkeypatch):
    monkeypatch.setenv("AI_REPLAY", "sometimes")
    with pytest.raises(ValidationError):
        get_settings()


def test_require_env_message(monkeypatch):
    monkeypatch.setattr("charie.shared.config.get_settings", lambda: Settings(charie_password=None))
    with pytest.raises(ConfigError) as raised:
        require_env("CHARIE_PASSWORD")
    assert str(raised.value) == (
        "CHARIE_PASSWORD is missing. Add it to .env on the laptop, "
        "or to the app's secrets on Azure."
    )


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("CHARIE_PASSWORD", "secret-word")
    assert require_env("CHARIE_PASSWORD") == "secret-word"


def test_require_env_unknown_name():
    with pytest.raises(ConfigError) as raised:
        require_env("NO_SUCH_SETTING")
    assert "NO_SUCH_SETTING is missing." in str(raised.value)
