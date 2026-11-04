"""Which connector speaks to which engine."""

from __future__ import annotations

from charie.config import Settings, get_settings
from charie.connectors.base import Caps, Connector, ConnectorError
from charie.connectors.postgres import POSTGRES_CAPS, PostgresConnector
from charie.connectors.sqlserver import SQLSERVER_CAPS, SqlServerConnector

__all__ = ["SUPPORTED_ENGINES", "caps_for", "connector_for", "require_supported"]

#: Engines this build can talk to.
SUPPORTED_ENGINES: frozenset[str] = frozenset({"pg", "mssql"})

#: And what to say about the ones it cannot.
_NOT_YET: dict[str, str] = {
    "mysql": "MySQL is a V1.1 connector (architecture Part 5.1).",
}


def require_supported(engine: str) -> None:
    """Refuse an engine we cannot speak, before anything else is attempted."""
    if engine in SUPPORTED_ENGINES:
        return

    pending = _NOT_YET.get(engine)
    if pending is not None:
        raise ConnectorError(f"No connector for engine {engine!r} yet. {pending}")
    raise ConnectorError(f"Unknown engine {engine!r}")


#: What each engine is, without asking one.
_CAPS: dict[str, Caps] = {"pg": POSTGRES_CAPS, "mssql": SQLSERVER_CAPS}


def caps_for(engine: str) -> Caps:
    """The engine's capabilities, with no connection and no credential."""
    require_supported(engine)
    return _CAPS[engine]


def connector_for(
    *,
    engine: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    tls_mode: str,
    settings: Settings | None = None,
) -> Connector:
    """Build the connector for one data source's stored settings."""
    require_supported(engine)
    resolved = settings if settings is not None else get_settings()

    if engine == "mssql":
        # No CA file: Microsoft's driver trusts the system store and offers no per-connection...
        return SqlServerConnector(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            tls_mode=tls_mode,
        )

    return PostgresConnector(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
        tls_mode=tls_mode,
        tls_ca_file=resolved.tls_ca_file,
    )
