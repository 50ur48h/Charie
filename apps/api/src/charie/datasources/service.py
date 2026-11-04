"""Registering data sources, and keeping their credentials out of this database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from charie.config import get_settings
from charie.connectors.base import Connector, ConnectorError, Health
from charie.connectors.factory import connector_for, require_supported
from charie.connectors.probe import check_reachable
from charie.connectors.tls import TLS_MODES, TlsPolicyError, resolve_tls_mode
from charie.db.models import DataSource
from charie.orgs.service import ConflictError, audit
from charie.secrets.base import SecretNotFoundError, SecretsProvider
from charie.secrets.factory import get_secrets_provider
from charie.secrets.local import SecretDecryptionError
from charie.tenancy.session import org_session

__all__ = [
    "DataSourceView",
    "NotFoundError",
    "connector_for_view",
    "create_data_source",
    "credentials_ref",
    "delete_data_source",
    "get_data_source",
    "list_data_sources",
    "test_data_source",
    "update_data_source",
]

STATUS_REGISTERED = "registered"
STATUS_VERIFIED = "verified"
STATUS_ERROR = "error"

#: How much of the username a response may carry (architecture Part 7.3).
USERNAME_HINT_CHARS = 4


class NotFoundError(Exception):
    """No such data source in this organization."""


def credentials_ref(org_id: uuid.UUID, data_source_id: uuid.UUID) -> str:
    """The reference under which one data source's credentials are stored."""
    return f"ds/{org_id}/{data_source_id}/credentials"


@dataclass(frozen=True, slots=True)
class DataSourceView:
    """What the rest of the application may know about a data source."""

    id: uuid.UUID
    name: str
    engine: str
    host: str
    port: int
    database: str
    host_display: str
    status: str
    secret_ref: str
    username_last4: str
    #: How much encryption this source's connections are opened with (B-013).
    tls_mode: str
    readonly_verified: bool
    last_verified_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime


# --- The non-secret half of a connection, as stored in data_sources.settings ---


def _display(host: str, port: int, database: str) -> str:
    """The human-readable address. Safe to log: it has never held a credential."""
    return f"{host}:{port}/{database}"


def _connection_settings(
    host: str, port: int, database: str, username_last4: str, tls_mode: str
) -> dict[str, object]:
    return {
        "host": host,
        "port": port,
        "database": database,
        # Not the username: the last of it.
        "username_last4": username_last4,
        "tls_mode": tls_mode,
    }


def _tls_mode(settings: dict[str, object], host: str) -> str:
    """The mode a row connects with — stored, or decided by policy for old rows."""
    stored = settings.get("tls_mode")
    if isinstance(stored, str) and stored in TLS_MODES:
        return stored
    return resolve_tls_mode(host=host, requested=None, settings=get_settings())


def _hint(username: str) -> str:
    return username[-USERNAME_HINT_CHARS:]


def _field(settings: dict[str, object], field: str) -> str:
    value = settings.get(field)
    if value is None:
        raise ValueError(f"data_sources.settings is missing {field!r}")
    return str(value)


def _port(settings: dict[str, object]) -> int:
    value = settings.get("port")
    if not isinstance(value, int):
        raise ValueError("data_sources.settings has no numeric 'port'")
    return value


def _view(row: DataSource) -> DataSourceView:
    settings = row.settings
    host = _field(settings, "host")
    return DataSourceView(
        id=row.id,
        name=row.name,
        engine=row.engine,
        host=host,
        port=_port(settings),
        database=_field(settings, "database"),
        host_display=row.host_display,
        status=row.status,
        secret_ref=row.secret_ref,
        username_last4=_field(settings, "username_last4"),
        tls_mode=_tls_mode(settings, host),
        readonly_verified=row.readonly_verified,
        last_verified_at=row.last_verified_at,
        created_by=row.created_by,
        created_at=row.created_at,
    )


# --- Operations ---


async def create_data_source(
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    name: str,
    engine: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    tls_mode: str | None = None,
    provider: SecretsProvider | None = None,
) -> DataSourceView:
    """Store the credentials, then record where the database is."""
    store = provider if provider is not None else get_secrets_provider()

    # First, and before the secret exists.
    mode = resolve_tls_mode(host=host, requested=tls_mode, settings=get_settings())

    data_source_id = uuid.uuid4()
    secret_ref = credentials_ref(org_id, data_source_id)
    host_display = _display(host, port, database)

    await store.put(secret_ref, {"username": username, "password": password})

    try:
        async with org_session(org_id) as session:
            row = DataSource(
                id=data_source_id,
                org_id=org_id,
                name=name,
                engine=engine,
                host_display=host_display,
                status=STATUS_REGISTERED,
                settings=_connection_settings(host, port, database, _hint(username), mode),
                secret_ref=secret_ref,
                created_by=actor_user_id,
            )
            session.add(row)
            # Flushed here so the view carries the database's own created_at and status rather...
            await session.flush()
            audit(
                session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                action="datasource.created",
                object_type="data_source",
                object_id=str(data_source_id),
                # host_display, the engine and how encrypted the connection is.
                details={
                    "name": name,
                    "engine": engine,
                    "host_display": host_display,
                    "tls_mode": mode,
                },
            )
            return _view(row)
    except IntegrityError as error:
        await store.delete(secret_ref)
        raise ConflictError(f"A data source named {name!r} already exists here") from error
    except Exception:
        # Any other failure would leave a credential nobody can reach.
        await store.delete(secret_ref)
        raise


async def list_data_sources(org_id: uuid.UUID) -> list[DataSourceView]:
    async with org_session(org_id) as session:
        rows = await session.execute(select(DataSource).order_by(DataSource.name))
        return [_view(row) for row in rows.scalars().all()]


async def get_data_source(org_id: uuid.UUID, data_source_id: uuid.UUID) -> DataSourceView:
    async with org_session(org_id) as session:
        row = (
            (await session.execute(select(DataSource).where(DataSource.id == data_source_id)))
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError("No such data source in this organization")
        return _view(row)


async def update_data_source(
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    data_source_id: uuid.UUID,
    name: str | None = None,
    host: str | None = None,
    port: int | None = None,
    database: str | None = None,
    username: str | None = None,
    password: str | None = None,
    tls_mode: str | None = None,
    provider: SecretsProvider | None = None,
) -> DataSourceView:
    """Rename, re-address, rotate credentials, or change the TLS mode."""
    store = provider if provider is not None else get_secrets_provider()

    async with org_session(org_id) as session:
        row = (
            (await session.execute(select(DataSource).where(DataSource.id == data_source_id)))
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError("No such data source in this organization")

        settings = dict(row.settings)
        changed: list[str] = []

        if name is not None and name != row.name:
            row.name = name
            changed.append("name")

        next_host = host if host is not None else _field(settings, "host")
        next_port = port if port is not None else _port(settings)
        next_database = database if database is not None else _field(settings, "database")
        if row.host_display != _display(next_host, next_port, next_database):
            changed.append("address")

        current_mode = _tls_mode(settings, _field(settings, "host"))
        next_tls_mode = _next_tls_mode(host=next_host, requested=tls_mode, current=current_mode)
        if next_tls_mode != current_mode:
            changed.append("tls")

        hint = _field(settings, "username_last4")
        if username is not None or password is not None:
            existing = await store.get(row.secret_ref)
            next_username = username if username is not None else existing.get("username", "")
            await store.put(
                row.secret_ref,
                {
                    "username": next_username,
                    "password": password if password is not None else existing.get("password", ""),
                },
            )
            hint = _hint(next_username)
            changed.append("credentials")

        row.settings = _connection_settings(
            next_host, next_port, next_database, hint, next_tls_mode
        )
        row.host_display = _display(next_host, next_port, next_database)

        if changed:
            # A verification describes the address and credentials it was run against.
            row.status = STATUS_REGISTERED
            row.readonly_verified = False
            row.last_verified_at = None
            audit(
                session,
                org_id=org_id,
                actor_user_id=actor_user_id,
                action="datasource.updated",
                object_type="data_source",
                object_id=str(data_source_id),
                # Which fields moved, never what they moved to.
                details={"fields": changed, "host_display": row.host_display},
            )

        return _view(row)


def _next_tls_mode(*, host: str, requested: str | None, current: str) -> str:
    """The mode after an update, which an address change can force upward."""
    settings = get_settings()
    if requested is not None:
        return resolve_tls_mode(host=host, requested=requested, settings=settings)
    try:
        return resolve_tls_mode(host=host, requested=current, settings=settings)
    except TlsPolicyError:
        return resolve_tls_mode(host=host, requested=None, settings=settings)


async def delete_data_source(
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    data_source_id: uuid.UUID,
    provider: SecretsProvider | None = None,
) -> None:
    store = provider if provider is not None else get_secrets_provider()

    async with org_session(org_id) as session:
        row = (
            (await session.execute(select(DataSource).where(DataSource.id == data_source_id)))
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError("No such data source in this organization")

        secret_ref, name = row.secret_ref, row.name
        await session.delete(row)
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="datasource.deleted",
            object_type="data_source",
            object_id=str(data_source_id),
            details={"name": name},
        )

    # After the commit.
    await store.delete(secret_ref)


async def test_data_source(
    *,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    data_source_id: uuid.UUID,
    provider: SecretsProvider | None = None,
) -> Health:
    """Is the address reachable, do the credentials work, and can they write?"""
    store = provider if provider is not None else get_secrets_provider()
    view = await get_data_source(org_id, data_source_id)

    health = await _verify(view, store)
    status = STATUS_VERIFIED if health.readonly_verified else STATUS_ERROR

    async with org_session(org_id) as session:
        row = (
            (await session.execute(select(DataSource).where(DataSource.id == data_source_id)))
            .scalars()
            .one_or_none()
        )
        if row is not None:
            row.status = status
            row.readonly_verified = health.readonly_verified
            if health.readonly_verified:
                # Only on success. The column answers "when was this last proven read-only".
                row.last_verified_at = health.checked_at
        audit(
            session,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="datasource.tested",
            object_type="data_source",
            object_id=str(data_source_id),
            # The detail is already sanitized by the connector.
            details={
                "reachable": health.reachable,
                "readonly_verified": health.readonly_verified,
                "status": status,
                "host_display": view.host_display,
                "detail": health.detail,
                # What was asked for, and what the far end actually did.
                "tls_mode": view.tls_mode,
                "tls_encrypted": health.tls.encrypted if health.tls is not None else None,
            },
        )

    return health


async def _verify(view: DataSourceView, store: SecretsProvider) -> Health:
    """The checks, cheapest and most local first."""
    try:
        require_supported(view.engine)
    except ConnectorError as error:
        return Health(
            reachable=False,
            readonly_verified=False,
            detail=str(error),
            checked_at=datetime.now(UTC),
        )

    reachability = await check_reachable(host=view.host, port=view.port)
    if not reachability.reachable:
        return Health(
            reachable=False,
            readonly_verified=False,
            detail=reachability.detail,
            checked_at=reachability.checked_at,
        )

    checked_at = datetime.now(UTC)
    try:
        credentials = await store.get(view.secret_ref)
    except (SecretNotFoundError, SecretDecryptionError) as error:
        return Health(
            reachable=True,
            readonly_verified=False,
            detail=(
                "The address answered, but this data source's stored credentials "
                f"could not be read: {error}"
            ),
            checked_at=checked_at,
        )

    try:
        connector = _connector(view, credentials)
    except ConnectorError as error:
        return Health(
            reachable=True, readonly_verified=False, detail=str(error), checked_at=checked_at
        )

    try:
        return await connector.test_connection()
    finally:
        # Whatever happened, the session on the customer's server ends here.
        await connector.aclose()


def _connector(view: DataSourceView, credentials: dict[str, str]) -> Connector:
    return connector_for(
        engine=view.engine,
        host=view.host,
        port=view.port,
        database=view.database,
        username=credentials.get("username", ""),
        password=credentials.get("password", ""),
        tls_mode=view.tls_mode,
    )


async def connector_for_view(
    view: DataSourceView, provider: SecretsProvider | None = None
) -> Connector:
    """An open-able connector for a registered data source."""
    require_supported(view.engine)
    store = provider if provider is not None else get_secrets_provider()
    return _connector(view, await store.get(view.secret_ref))
