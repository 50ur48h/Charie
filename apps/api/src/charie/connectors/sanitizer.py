"""Scrubbing connector errors before anyone can read them."""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["REDACTED", "sanitize", "sanitize_exception"]

REDACTED = "[redacted]"

#: Applied in order.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # postgresql://user:secret@host:5432/db — everything after the scheme goes.
    (re.compile(r"\b([a-zA-Z][a-zA-Z0-9+.\-]*)://[^\s'\"<>,;)\]]+"), rf"\1://{REDACTED}"),
    # An auth header carries a scheme before the credential.
    (
        re.compile(
            r"(?i)\bauthorization\s*[=:]\s*(?:bearer|basic|digest|negotiate)?\s*[^\s;,)\"']+"
        ),
        f"authorization={REDACTED}",
    ),
    # ODBC and libpq keyword form. The key survives; the value never does.
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|pass|secret|token|api[_-]?key|access[_-]?key|sas"
            r"|credential|authorization)\b\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s;,)\"']+)"
        ),
        rf"\1={REDACTED}",
    ),
    # The rest of a connection string: where it points and who it connects as.
    (
        re.compile(
            r"(?i)\b(hostaddr|hostname|host|server|address|addr|data\s+source"
            r"|initial\s+catalog|database|dbname|username|user\s+id|uid|user)\b"
            r"\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s;,)\"']+)"
        ),
        rf"\1={REDACTED}",
    ),
    # Resolver failures name the host in prose rather than as a key=value pair.
    (re.compile(r"(?i)\bhost\s*name\s*\"[^\"]*\""), f'host name "{REDACTED}"'),
    (
        re.compile(
            r"(?i)\b(name or service not known|not known|unknown host|no such host)"
            r"\s*:\s*[^\s;,)\"']+"
        ),
        rf"\1: {REDACTED}",
    ),
    # SQL Server's tcp:host,1433 form, which carries no key to match on.
    (re.compile(r"(?i)\btcp:[^\s;,)\]]+(?:,\s*\d{1,5})?"), f"tcp:{REDACTED}"),
    # Python prints a failed connect as ('10.1.2.3', 5432) or ('db.corp', 5432).
    (
        re.compile(r"\((['\"])[^'\"]+\1\s*,\s*\d{1,5}\)"),
        f"({REDACTED}, {REDACTED})",
    ),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?\b"), REDACTED),
    # Bracketed IPv6, with or without a port.
    (re.compile(r"\[[0-9A-Fa-f]*:[0-9A-Fa-f:]+\](?::\d{1,5})?"), REDACTED),
    # A dotted name with a port is an address, whatever it is called.
    (
        re.compile(r"\b[A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z][A-Za-z0-9-]{1,62}:\d{1,5}\b"),
        REDACTED,
    ),
)

#: Around a known value: not a word character, a dot or a dash.
_LEFT = r"(?<![\w.\-])"
_RIGHT = r"(?![\w.\-])"


def sanitize(message: str, *, known: Iterable[str] = ()) -> str:
    """Return ``message`` with credentials, addresses and identities removed."""
    scrubbed = message

    # Longest first, so redacting "db" cannot leave a fragment of "db.corp.net" behind for the...
    for value in sorted({v for v in known if v and v.strip()}, key=len, reverse=True):
        scrubbed = re.sub(_LEFT + re.escape(value.strip()) + _RIGHT, REDACTED, scrubbed)

    for pattern, replacement in _PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)

    return scrubbed


def sanitize_exception(error: BaseException, *, known: Iterable[str] = ()) -> str:
    """A one-line, safe rendering of a connector failure."""
    detail = sanitize(str(error), known=known).strip()
    name = type(error).__name__
    return f"{name}: {detail}" if detail else name
