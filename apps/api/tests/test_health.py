"""Tests for ``GET /healthz``."""

from __future__ import annotations

from typing import cast

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from charie.config import Settings
from charie.main import create_app


async def test_healthz_returns_ok_with_build_identity(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["git_sha"] == "testsha"
    assert body["version"]
    assert body["missing_settings"] == []


async def test_healthz_is_degraded_when_the_mode_cannot_be_served() -> None:
    """The case that shipped. `AUTH_MODE=entra` with no authority is a configuration that boots."""
    app = create_app(
        settings=Settings(  # pyright: ignore[reportArgumentType]
            # Pinned off the repository's `.env`, and this test is why (B-032's family).
            _env_file=None,  # pyright: ignore[reportCallIssue]
            auth_mode="entra",
            oidc_authority=None,
            secrets_backend="local",
            local_secrets_key=SecretStr("x"),
            llm_models={"openai": {"small": "s", "mid": "m", "strong": "l"}},
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        response = await ac.get("/healthz")

    # 200, deliberately: the process is alive and an orchestrator restarting it would fix nothing.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["missing_settings"] == ["OIDC_AUTHORITY"]


async def test_healthz_reports_the_configured_git_sha() -> None:
    """The probe identifies the build, so a stale revision is visible in seconds."""
    app = create_app(settings=Settings(git_sha="deadbeef"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        body = (await ac.get("/healthz")).json()

    assert body["git_sha"] == "deadbeef"


async def test_healthz_leaks_no_configuration(client: AsyncClient) -> None:
    """An unauthenticated endpoint may expose build identity and nothing else."""
    body = (await client.get("/healthz")).json()

    assert set(body) == {
        "status",
        "version",
        "git_sha",
        "missing_settings",
        "unservable_roles",
    }
    assert all(name.isupper() for name in body["missing_settings"])


async def test_a_degraded_probe_names_variables_and_never_values() -> None:
    """The leak this could have been. Everything reported is a name."""
    app = create_app(
        settings=Settings(  # pyright: ignore[reportArgumentType]
            # Pinned off the repository's `.env`, and this test is why (B-032's family).
            _env_file=None,  # pyright: ignore[reportCallIssue]
            auth_mode="entra",
            oidc_authority=None,
            secrets_backend="keyvault",
            key_vault_url=None,
            artifacts_backend="blob",
            artifacts_account_url=None,
            git_sha="testsha",
            llm_models={"openai": {"small": "s", "mid": "m", "strong": "l"}},
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        body = (await ac.get("/healthz")).json()

    assert body["missing_settings"] == [
        "ARTIFACTS_ACCOUNT_URL",
        "KEY_VAULT_URL",
        "OIDC_AUTHORITY",
    ]
    # Nothing in the payload is a URL, a key, or anything but a name and a sha.
    rendered = str(body)
    assert "://" not in rendered


async def test_healthz_is_degraded_when_no_model_can_serve_a_run() -> None:
    """The case that shipped after the one above (B-126)."""
    app = create_app(
        settings=Settings(  # pyright: ignore[reportArgumentType]
            # Pinned off the repository's `.env`, and this test is why (B-032's family).
            _env_file=None,  # pyright: ignore[reportCallIssue]
            auth_mode="entra",
            oidc_authority="https://x.ciamlogin.com/t/v2.0",
            secrets_backend="local",
            local_secrets_key=SecretStr("x"),
            llm_providers=("openai",),
            llm_models={},
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        response = await ac.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["missing_settings"] == ["LLM_MODELS"]


async def test_healthz_is_degraded_when_one_provider_of_several_has_no_models() -> None:
    """The fallback chain is the half a presence check cannot see at all."""
    app = create_app(
        settings=Settings(  # pyright: ignore[reportArgumentType]
            # Pinned off the repository's `.env`, and this test is why (B-032's family).
            _env_file=None,  # pyright: ignore[reportCallIssue]
            auth_mode="entra",
            oidc_authority="https://x.ciamlogin.com/t/v2.0",
            secrets_backend="local",
            local_secrets_key=SecretStr("x"),
            llm_providers=("openai", "anthropic"),
            llm_models={"openai": {"small": "s", "mid": "m", "strong": "l"}},
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        body = (await ac.get("/healthz")).json()

    assert body["status"] == "degraded"
    assert body["missing_settings"] == ["LLM_MODELS"]


# --- A role that resolves to no model (B-154) ---


def _settings(**overrides: object) -> Settings:
    """A servable configuration, pinned off the repository's `.env`."""
    base: dict[str, object] = {
        "_env_file": None,
        # `dev`, so `missing_for_mode` is empty and the probe reaches the role check at all.
        "auth_mode": "dev",
        "secrets_backend": "local",
        "local_secrets_key": SecretStr("x"),
        "llm_providers": ("openai",),
        "llm_models": {"openai": {"small": "s", "strong": "l"}},
    }
    base.update(overrides)
    return Settings(**base)  # pyright: ignore[reportArgumentType, reportCallIssue]


async def _probe(settings: Settings) -> dict[str, object]:
    app = create_app(settings=settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        body: dict[str, object] = (await ac.get("/healthz")).json()
        return body


def _unservable(body: dict[str, object]) -> list[str]:
    """The probe's role failures, typed once rather than cast in every case."""
    return cast(list[str], body["unservable_roles"])


async def test_a_role_mapped_to_a_tier_no_model_fills_is_degraded() -> None:
    """The hole that made removing an unused model unsafe."""
    body = await _probe(_settings(llm_role_map={"compose": "mid"}))

    assert body["status"] == "degraded"
    unservable = _unservable(body)
    assert len(unservable) == 1
    assert unservable[0].startswith("compose:")
    # It says which tier is missing, because that is the fix.
    assert "mid" in unservable[0]


async def test_dropping_a_model_no_role_calls_leaves_the_probe_healthy() -> None:
    """And this is what makes the removal a tidy rather than a trap (B-154)."""
    body = await _probe(_settings(llm_role_map={"compose": "small"}))

    assert body["status"] == "ok"
    assert body["unservable_roles"] == []


async def test_dropping_mid_is_safe_only_while_compose_is_mapped_off_it() -> None:
    """The coupling the removal rests on, asserted rather than assumed."""
    with_override = await _probe(_settings(llm_role_map={"compose": "small"}))
    assert with_override["unservable_roles"] == []
    assert with_override["status"] == "ok"

    without_override = await _probe(_settings())
    assert [entry.split(":")[0] for entry in _unservable(without_override)] == ["compose"], (
        "compose is the only role defaulting to `mid`; if another one now does, "
        "the deployment that dropped `mid` needs to know before it ships"
    )


async def test_the_probe_names_roles_and_tiers_but_never_a_credential() -> None:
    """The rule `missing_settings` follows, extended to the new field."""
    body = await _probe(
        _settings(llm_role_map={"sql": "mid"}, local_secrets_key=SecretStr("super-secret-value"))
    )

    assert "super-secret-value" not in str(body)
    assert _unservable(body)[0].startswith("sql:")
