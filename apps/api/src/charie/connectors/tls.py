"""How encrypted a connection to a customer database has to be (B-013)."""

from __future__ import annotations

import ssl
from collections.abc import Sequence
from ipaddress import ip_address
from pathlib import Path
from typing import get_args

from charie.config import EncryptedTlsMode, Settings, TlsMode

__all__ = [
    "ENCRYPTED_TLS_MODES",
    "OPTIONAL_TLS_MODES",
    "TLS_MODES",
    "VERIFYING_TLS_MODES",
    "TlsPolicyError",
    "describe_verification",
    "is_local_host",
    "odbc_parameters",
    "resolve_tls_mode",
    "ssl_parameter",
    "tls_detail",
]

#: Every mode this product understands, in increasing order of strictness.
TLS_MODES: tuple[str, ...] = get_args(TlsMode)

#: The ones that guarantee an encrypted connection.
ENCRYPTED_TLS_MODES: tuple[str, ...] = get_args(EncryptedTlsMode)

#: The ones that permit a plaintext connection.
OPTIONAL_TLS_MODES: frozenset[str] = frozenset(set(TLS_MODES) - set(ENCRYPTED_TLS_MODES))

#: The ones that also check who they are talking to.
VERIFYING_TLS_MODES: frozenset[str] = frozenset({"verify-ca", "verify-full"})

#: Names that always mean this machine.
_LOCAL_NAMES: frozenset[str] = frozenset({"localhost", "host.docker.internal"})


class TlsPolicyError(ValueError):
    """A data source asked for less encryption than its address allows."""


def is_local_host(host: str, *, also_local: Sequence[str] = ()) -> bool:
    """Is this address on the machine the API runs on?"""
    name = _normalise(host)
    if not name:
        return False
    if name in _LOCAL_NAMES or name.endswith(".localhost"):
        return True
    if any(name == _normalise(entry) for entry in also_local):
        return True
    try:
        return ip_address(name).is_loopback
    except ValueError:
        # A hostname, not an address.
        return False


def resolve_tls_mode(*, host: str, requested: str | None, settings: Settings) -> str:
    """The mode this data source will connect with, or a refusal."""
    local = not settings.is_production and is_local_host(host, also_local=settings.tls_local_hosts)
    mode = requested if requested is not None else _default_mode(local=local, settings=settings)

    if mode not in TLS_MODES:
        raise TlsPolicyError(f"Unknown TLS mode {mode!r}. Choose one of: {', '.join(TLS_MODES)}.")
    if mode in OPTIONAL_TLS_MODES and not local:
        raise TlsPolicyError(
            f"TLS mode {mode!r} allows an unencrypted connection, which is only "
            f"permitted for a database on this machine — {host!r} is not one. "
            f"Use one of: {', '.join(ENCRYPTED_TLS_MODES)}."
        )
    return mode


def ssl_parameter(mode: str, ca_file: Path | None = None) -> str | ssl.SSLContext:
    """What the driver is handed for this mode."""
    if mode not in TLS_MODES:
        raise TlsPolicyError(f"Unknown TLS mode {mode!r}. Choose one of: {', '.join(TLS_MODES)}.")
    if mode not in VERIFYING_TLS_MODES:
        return mode

    try:
        context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
    except OSError as error:
        # Names the setting, not the path: this message can reach a tenant admin.
        raise TlsPolicyError(
            "TLS_CA_FILE could not be read, so no certificate can be verified."
        ) from error

    context.verify_mode = ssl.CERT_REQUIRED
    # verify-ca trusts the chain and accepts any name in it.
    context.check_hostname = mode == "verify-full"
    return context


def odbc_parameters(mode: str) -> dict[str, str]:
    """The same ladder, in Microsoft's ODBC driver's vocabulary (WP3.3)."""
    if mode not in TLS_MODES:
        raise TlsPolicyError(f"Unknown TLS mode {mode!r}. Choose one of: {', '.join(TLS_MODES)}.")
    if mode == "disable":
        return {"encrypt": "no"}
    return {
        "encrypt": "yes",
        "trustservercertificate": "no" if mode in VERIFYING_TLS_MODES else "yes",
    }


def tls_detail(
    *, mode: str, encrypted: bool, version: str | None = None, cipher: str | None = None
) -> str:
    """The one line a test result shows about encryption."""
    if not encrypted:
        return f"{mode} — this connection is NOT encrypted"

    negotiated = ", ".join(part for part in (version, cipher) if part)
    suffix = f" with {negotiated}" if negotiated else ""
    return f"{mode} — encrypted{suffix}; {describe_verification(mode)}"


def describe_verification(mode: str) -> str:
    """What an encrypted connection in this mode checked, and what it did not."""
    if mode == "verify-full":
        return "the certificate and host name were verified"
    if mode == "verify-ca":
        return "the certificate was verified against a trusted CA"
    return "the server certificate was not verified"


def _default_mode(*, local: bool, settings: Settings) -> str:
    return settings.tls_mode_local if local else settings.tls_mode


def _normalise(host: str) -> str:
    """Lower-cased, unbracketed, without the trailing dot of an absolute name."""
    name = host.strip().rstrip(".").lower()
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    return name
