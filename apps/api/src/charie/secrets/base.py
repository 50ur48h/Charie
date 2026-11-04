"""The provider protocol and the shape of a reference."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol

__all__ = [
    "InvalidSecretRefError",
    "SecretNotFoundError",
    "SecretsProvider",
    "validate_ref",
]

#: Conservative on purpose: letters, digits and the three separators a reference needs.
_VALID_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")


class SecretNotFoundError(LookupError):
    """Nothing is stored under that reference."""


class InvalidSecretRefError(ValueError):
    """A reference that no backend will be asked to interpret."""


def validate_ref(secret_ref: str) -> str:
    """Return the reference, or refuse it."""
    if ".." in secret_ref or _VALID_REF.match(secret_ref) is None:
        raise InvalidSecretRefError(f"Not a usable secret reference: {secret_ref!r}")
    return secret_ref


class SecretsProvider(Protocol):
    """Where credentials live. Implementations must never log a value."""

    async def put(self, secret_ref: str, value: Mapping[str, str]) -> None:
        """Store (or replace) the credential under ``secret_ref``."""
        ...

    async def get(self, secret_ref: str) -> dict[str, str]:
        """Fetch the credential, or raise ``SecretNotFoundError``."""
        ...

    async def delete(self, secret_ref: str) -> None:
        """Remove the credential. Idempotent: deleting nothing is a success."""
        ...
