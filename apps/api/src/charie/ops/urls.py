"""Turn DATABASE_URL into the two URLs Charie needs, printed as shell exports for start.sh."""

from __future__ import annotations

import os
import shlex
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

APP_ROLE = "charie_app"
DRIVER = "postgresql+asyncpg"


def with_driver(url: str) -> str:
    """postgres:// or postgresql:// (as hosting providers give it) in the form SQLAlchemy needs."""
    parts = urlsplit(url)
    if parts.scheme in ("postgres", "postgresql"):
        parts = parts._replace(scheme=DRIVER)
    # asyncpg spells libpq's `sslmode` as `ssl`.
    query = [("ssl" if key == "sslmode" else key, value) for key, value in parse_qsl(parts.query)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def app_url(owner_url: str, password: str) -> str:
    """The owner URL, connecting as charie_app instead: same host, database and options."""
    parts = urlsplit(with_driver(owner_url))
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{APP_ROLE}:{quote(password, safe='')}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit(parts._replace(netloc=netloc))


def exports(env: dict[str, str]) -> list[str]:
    owner = env.get("DATABASE_URL", "").strip()
    if not owner:
        return []
    lines = [f"export DATABASE_URL={shlex.quote(with_driver(owner))}"]
    configured = env.get("APP_DATABASE_URL", "").strip()
    if configured:
        lines.append(f"export APP_DATABASE_URL={shlex.quote(with_driver(configured))}")
    elif env.get("APP_DB_PASSWORD"):
        url = app_url(owner, env["APP_DB_PASSWORD"])
        lines.append(f"export APP_DATABASE_URL={shlex.quote(url)}")
    return lines


if __name__ == "__main__":
    print("\n".join(exports(dict(os.environ))))
