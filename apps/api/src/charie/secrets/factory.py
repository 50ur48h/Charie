"""Choosing a backend — and refusing the wrong one."""

from __future__ import annotations

from functools import lru_cache

from charie.config import Settings, get_settings
from charie.secrets.base import SecretsProvider
from charie.secrets.local import LocalSecretsProvider

__all__ = ["build_secrets_provider", "get_secrets_provider"]


def build_secrets_provider(settings: Settings | None = None) -> SecretsProvider:
    """The provider this deployment is configured for."""
    resolved = settings if settings is not None else get_settings()
    resolved.assert_secrets_backend_is_production_safe()

    if resolved.secrets_backend == "keyvault":
        # Imported here rather than at module scope: this module is imported by every process.
        from charie.secrets.keyvault import KeyVaultSecretsProvider

        return KeyVaultSecretsProvider(vault_url=resolved.key_vault_url or "")

    return LocalSecretsProvider(
        key=resolved.require_local_secrets_key(),
        path=resolved.resolve_local_secrets_path(),
    )


@lru_cache(maxsize=1)
def get_secrets_provider() -> SecretsProvider:
    """The process-wide provider, built on first use."""
    return build_secrets_provider()
