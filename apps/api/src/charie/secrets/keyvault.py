"""The deployed backend: Azure Key Vault, reached by managed identity (WP12.2)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from charie.secrets.base import (
    InvalidSecretRefError,
    SecretNotFoundError,
    validate_ref,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from azure.keyvault.secrets.aio import SecretClient

__all__ = ["KeyVaultSecretsProvider", "secret_name_for"]

#: What Key Vault accepts for a secret name: letters, digits and hyphens.
_VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,126}$")


def secret_name_for(secret_ref: str) -> str:
    """The vault name for a reference, or a refusal."""
    validate_ref(secret_ref)
    if "." in secret_ref or "_" in secret_ref:
        raise InvalidSecretRefError(
            f"Key Vault names cannot carry '.' or '_', and folding them onto '-' "
            f"would let two references share one secret: {secret_ref!r}"
        )
    name = secret_ref.replace("/", "-")
    if _VALID_NAME.match(name) is None:
        raise InvalidSecretRefError(
            f"{secret_ref!r} does not translate to a usable Key Vault name ({name!r})"
        )
    return name


class KeyVaultSecretsProvider:
    """A ``SecretsProvider`` backed by one Key Vault."""

    def __init__(self, *, vault_url: str, client: SecretClient | None = None) -> None:
        if not vault_url:
            raise RuntimeError(
                "SECRETS_BACKEND=keyvault needs KEY_VAULT_URL. The deployment sets it "
                "from the vault the Bicep created; without it there is nowhere to "
                "store customer credentials and the API must not pretend otherwise."
            )
        self._vault_url = vault_url
        if client is not None:
            self._client = client
            return
        # Deferred: see the module docstring.
        from azure.identity.aio import DefaultAzureCredential
        from azure.keyvault.secrets.aio import SecretClient as _SecretClient

        self._client = _SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

    async def put(self, secret_ref: str, value: Mapping[str, str]) -> None:
        """Store (or replace) the credential."""
        name = secret_name_for(secret_ref)
        # `sort_keys` so an unchanged credential serialises identically and does not create a...
        payload = json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
        await self._client.set_secret(name, payload)

    async def get(self, secret_ref: str) -> dict[str, str]:
        """Fetch the credential, or raise ``SecretNotFoundError``."""
        from azure.core.exceptions import ResourceNotFoundError

        name = secret_name_for(secret_ref)
        try:
            secret = await self._client.get_secret(name)
        except ResourceNotFoundError as error:
            raise SecretNotFoundError(f"No credential stored under {secret_ref!r}") from error

        if secret.value is None:
            # A secret with no value is a row/store disagreement, not a key problem.
            raise SecretNotFoundError(f"No credential stored under {secret_ref!r}")
        # The message deliberately names the reference and never the value.
        try:
            loaded = cast(dict[str, Any], json.loads(secret.value))
        except json.JSONDecodeError as error:
            raise SecretNotFoundError(
                f"The credential stored under {secret_ref!r} is not readable JSON"
            ) from error
        return {str(k): str(v) for k, v in loaded.items()}

    async def delete(self, secret_ref: str) -> None:
        """Remove the credential. Idempotent, as the interface requires."""
        from azure.core.exceptions import ResourceNotFoundError

        name = secret_name_for(secret_ref)
        try:
            await self._client.delete_secret(name)
        except ResourceNotFoundError:
            return

    async def aclose(self) -> None:
        """Release the client's transport. Used by tests and by shutdown."""
        await self._client.close()
