"""What a mode requires, declared once and checked in both directions."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import SecretStr

from charie.config import MODE_REQUIREMENTS, RUN_REQUIRED, Settings

CHECK_ENV = Path(__file__).resolve().parents[3] / "scripts" / "check_env.sh"


def _shell_table() -> set[tuple[str, str, str]]:
    """`KEY | VALUE | COMPANION` rows out of BACKEND_REQUIRES."""
    text = CHECK_ENV.read_text(encoding="utf-8")
    block = re.search(r"readonly BACKEND_REQUIRES='\n(.*?)\n'", text, re.S)
    assert block, "BACKEND_REQUIRES not found in check_env.sh"
    rows: set[tuple[str, str, str]] = set()
    for line in block.group(1).splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        assert len(parts) == 3, f"malformed row: {line!r}"
        rows.add((parts[0], parts[1], parts[2]))
    return rows


def _python_table() -> set[tuple[str, str, str]]:
    return {
        (field.upper(), value, required.upper())
        for (field, value), names in MODE_REQUIREMENTS.items()
        for required in names
    }


def test_the_shell_copy_matches_the_declaration() -> None:
    """Drift here means the templates stop being checked for a mode, silently."""
    deployable = {row for row in _python_table() if row[1] != "local"}

    assert deployable == _shell_table(), (
        "MODE_REQUIREMENTS and check_env.sh's BACKEND_REQUIRES disagree. Add the "
        "row to the shell table so the deployment templates are checked for it — "
        "otherwise a mode can be selected in Bicep with nothing to satisfy it, "
        "which is exactly how AUTH_MODE=entra shipped without OIDC_AUTHORITY."
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"auth_mode": "entra", "oidc_authority": None}, ["OIDC_AUTHORITY"]),
        ({"auth_mode": "entra", "oidc_authority": "  "}, ["OIDC_AUTHORITY"]),
        ({"auth_mode": "entra", "oidc_authority": "https://x/v2.0"}, []),
        ({"secrets_backend": "keyvault", "key_vault_url": None}, ["KEY_VAULT_URL"]),
        (
            {"secrets_backend": "keyvault", "key_vault_url": "https://v.vault.azure.net/"},
            [],
        ),
        (
            {"artifacts_backend": "blob", "artifacts_account_url": None},
            ["ARTIFACTS_ACCOUNT_URL"],
        ),
    ],
)
def test_missing_for_mode_names_what_is_missing(
    overrides: dict[str, object], expected: list[str]
) -> None:
    """A blank string counts as missing: `OIDC_AUTHORITY=` in a template is not a value."""
    base: dict[str, object] = {
        # Pinned off the repository's `.env`: pydantic-settings deep-merges dict fields.
        "_env_file": None,
        "auth_mode": "dev",
        "secrets_backend": "local",
        "local_secrets_key": SecretStr("x"),
        "artifacts_backend": "local",
        "oidc_authority": None,
        "key_vault_url": None,
        "artifacts_account_url": None,
        # Servable, so each case below isolates the one thing it varies.
        "llm_models": {"openai": {"small": "s", "mid": "m", "strong": "l"}},
    }
    settings = Settings(**(base | overrides))  # pyright: ignore[reportArgumentType]

    assert settings.missing_for_mode() == expected


def test_a_complete_configuration_is_not_degraded() -> None:
    """The control."""
    settings = Settings(  # pyright: ignore[reportArgumentType]
        _env_file=None,  # pyright: ignore[reportCallIssue]
        auth_mode="entra",
        oidc_authority="https://x.ciamlogin.com/t/v2.0",
        secrets_backend="keyvault",
        key_vault_url="https://v.vault.azure.net/",
        artifacts_backend="blob",
        artifacts_account_url="https://s.blob.core.windows.net/",
        llm_models={"openai": {"small": "s", "mid": "m", "strong": "l"}},
    )

    assert settings.missing_for_mode() == []


# --- RUN_REQUIRED: what no mode makes optional -------------------------------


def _shell_run_required() -> set[str]:
    """`KEY | why` rows out of check_env.sh's RUN_REQUIRED."""
    text = CHECK_ENV.read_text(encoding="utf-8")
    block = re.search(r"readonly RUN_REQUIRED='\n(.*?)\n'", text, re.S)
    assert block, "RUN_REQUIRED not found in check_env.sh"
    keys: set[str] = set()
    for line in block.group(1).splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        assert len(parts) == 2, f"malformed row: {line!r}"
        assert parts[1], f"{parts[0]} has no reason beside it"
        keys.add(parts[0])
    return keys


def test_the_shell_copy_of_run_required_matches_the_declaration() -> None:
    """The second copy, kept true the same way the first one is."""
    assert {name.upper() for name in RUN_REQUIRED} == _shell_run_required(), (
        "RUN_REQUIRED and check_env.sh's copy disagree. Add the row to the shell "
        "table with the reason beside it, so the deployment templates are checked "
        "for it."
    )


def test_no_name_is_required_both_always_and_conditionally() -> None:
    """The control on the split between the two tables."""
    conditional = {name.upper() for names in MODE_REQUIREMENTS.values() for name in names}

    assert not (conditional & {name.upper() for name in RUN_REQUIRED})


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        # The configuration that shipped: a credential and no model map.
        ({"llm_providers": ("openai",), "llm_models": {}}, ["LLM_MODELS"]),
        # Set, non-empty, and about a provider nobody configured.
        (
            {"llm_providers": ("openai",), "llm_models": {"anthropic": {"small": "s"}}},
            ["LLM_MODELS"],
        ),
        # The fallback chain, which only matters during an incident.
        (
            {
                "llm_providers": ("openai", "anthropic"),
                "llm_models": {"openai": {"small": "s"}},
            },
            ["LLM_MODELS"],
        ),
        # Empty chain: nothing can serve any role.
        ({"llm_providers": (), "llm_models": {}}, ["LLM_PROVIDERS"]),
        # The control. Every provider named has models, so nothing is reported.
        (
            {
                "llm_providers": ("openai",),
                "llm_models": {"openai": {"small": "s", "mid": "m", "strong": "l"}},
            },
            [],
        ),
    ],
)
def test_missing_for_mode_covers_the_model_configuration(
    overrides: dict[str, object], expected: list[str]
) -> None:
    """What `/healthz` reports `degraded` from, at the level below the route."""
    base: dict[str, object] = {
        # Pinned off the repository's `.env`: pydantic-settings deep-merges dict fields.
        "_env_file": None,
        "auth_mode": "dev",
        "secrets_backend": "local",
        "local_secrets_key": SecretStr("x"),
        "artifacts_backend": "local",
    }
    settings = Settings(**(base | overrides))  # pyright: ignore[reportArgumentType]

    assert settings.missing_for_mode() == expected
