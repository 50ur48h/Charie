"""Tests for settings resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from charie.config import Settings, find_env_file, get_settings


def test_defaults_are_safe_for_local_development() -> None:
    """The app must boot with no configuration at all."""
    settings = Settings()

    assert settings.env == "local"
    assert settings.build_env == "dev"
    assert settings.git_sha == "unknown"
    assert settings.cors_origins == ("http://localhost:3000",)


def test_the_default_auth_mode_is_the_strict_one() -> None:
    """Forgetting to configure auth must not hand you a token-minting process."""
    assert Settings.model_fields["auth_mode"].default == "entra"


def test_cors_origins_from_env_accepts_a_comma_separated_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real path: compose and Container Apps both pass env vars as strings."""
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://app.example.com")

    assert Settings().cors_origins == ("http://localhost:3000", "https://app.example.com")


def test_cors_origins_from_env_accepts_a_json_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.example.com"]')

    assert Settings().cors_origins == ("https://a.example.com",)


def test_cors_origins_rejects_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken origins list must fail at boot, not silently allow nothing."""
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.example.com"')

    with pytest.raises(ValueError, match="cors_origins"):
        Settings()


def test_unknown_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in ENV must fail loudly at boot, not silently pick a weaker mode."""
    monkeypatch.setenv("ENV", "produciton")

    with pytest.raises(ValueError, match="env"):
        Settings()


def test_a_variable_set_to_nothing_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B-090. ``DAL_MAX_ROWS: ${DAL_MAX_ROWS."""
    monkeypatch.setenv("DAL_MAX_ROWS", "")
    monkeypatch.setenv("EMBEDDINGS_DIMENSIONS", "")
    monkeypatch.setenv("ARTIFACT_RETENTION_DAYS", "  ")

    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.dal_max_rows == Settings.model_fields["dal_max_rows"].default
    assert settings.embeddings_dimensions == 1536
    assert settings.artifact_retention_days == 30


def test_a_variable_set_to_nothing_is_not_the_empty_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty means unset, never "the empty string"."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OIDC_ISSUER", "")

    settings = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert settings.openai_api_key is None
    assert settings.oidc_issuer is None


def test_settings_are_immutable() -> None:
    settings = Settings()

    with pytest.raises(ValueError, match="frozen"):
        settings.git_sha = "tampered"  # pyright: ignore[reportAttributeAccessIssue]


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_find_env_file_survives_a_shallow_path() -> None:
    """Regression: the container layout has fewer ancestors than the repo layout."""
    assert find_env_file(Path("/app/src/charie/config.py")) is None


def test_find_env_file_locates_a_dot_env_above_it(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ENV=local\n", encoding="utf-8")
    nested = tmp_path / "apps" / "api" / "src"
    nested.mkdir(parents=True)

    assert find_env_file(nested / "config.py") == tmp_path / ".env"


def test_the_app_boots_with_no_identity_provider_configured() -> None:
    """The promise from WP0.2: /healthz answers on a bare checkout."""
    from charie.main import create_app

    app = create_app(settings=Settings(env="ci", build_env="dev", auth_mode="entra"))

    assert app.state.token_validator is None


def test_audiences_split_on_commas() -> None:
    settings = Settings(oidc_audience="api://abc, abc")

    assert settings.resolve_audiences() == ["api://abc", "abc"]


def test_a_single_audience_still_works() -> None:
    assert Settings(oidc_audience="charie-api").resolve_audiences() == ["charie-api"]


# --- The DSN the deployment hands over in two halves (WP12.2, B-120) ---


def _app_settings(**overrides: object) -> Settings:
    # `app_db_password` is pinned to None in the base, not merely left out.
    base: dict[str, object] = {
        "app_database_url": "postgresql+asyncpg://u@h:5432/d?ssl=require",
        "app_db_password": None,
    }
    return Settings(**(base | overrides))  # pyright: ignore[reportArgumentType]


def test_the_password_is_joined_to_a_dsn_that_omits_it() -> None:
    """`apps.bicep` keeps the password as the only part that comes from the vault."""
    settings = _app_settings(app_db_password=SecretStr("pa55"))

    assert settings.require_app_database_url() == "postgresql+asyncpg://u:pa55@h:5432/d?ssl=require"


def test_a_password_needing_escaping_survives_the_join() -> None:
    """A generated password contains `@` and `/` often enough that not escaping would work in..."""
    settings = _app_settings(app_db_password=SecretStr("p@ss/w:rd"))

    assert "p%40ss%2Fw%3Ard@h:5432" in settings.require_app_database_url()


def test_a_dsn_that_already_carries_one_is_left_alone() -> None:
    """Local `.env` embeds the password."""
    settings = _app_settings(
        app_database_url="postgresql+asyncpg://u:already@h:5432/d",
        app_db_password=SecretStr("ignored"),
    )

    assert settings.require_app_database_url() == "postgresql+asyncpg://u:already@h:5432/d"


def test_no_password_setting_leaves_the_dsn_untouched() -> None:
    assert _app_settings().require_app_database_url().startswith("postgresql+asyncpg://u@h")


def test_the_password_does_not_surface_in_a_settings_dump() -> None:
    """SecretStr for the reason LOCAL_SECRETS_KEY is: a settings dump reaches logs."""
    settings = _app_settings(app_db_password=SecretStr("pa55"))

    assert "pa55" not in repr(settings)
    assert "pa55" not in str(settings.model_dump())
