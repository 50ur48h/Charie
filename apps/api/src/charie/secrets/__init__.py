"""Credential storage, behind one interface (architecture Part 7.3)."""

from __future__ import annotations

from charie.secrets.base import (
    InvalidSecretRefError,
    SecretNotFoundError,
    SecretsProvider,
    validate_ref,
)
from charie.secrets.factory import build_secrets_provider, get_secrets_provider
from charie.secrets.keyvault import KeyVaultSecretsProvider, secret_name_for
from charie.secrets.local import LocalSecretsProvider, SecretDecryptionError

__all__ = [
    "InvalidSecretRefError",
    "KeyVaultSecretsProvider",
    "LocalSecretsProvider",
    "SecretDecryptionError",
    "SecretNotFoundError",
    "SecretsProvider",
    "build_secrets_provider",
    "get_secrets_provider",
    "secret_name_for",
    "validate_ref",
]
