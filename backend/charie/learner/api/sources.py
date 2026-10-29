"""`GET`/`PUT /api/sources/database` and the connection test (06, P04.2)."""

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from charie.shared.connectors.base import ConnectorError
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.crypto import decrypt_text, encrypt_text
from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.tables.sources import DataSource

sources_router = APIRouter()


class DatabaseInput(BaseModel):
    kind: str = "postgres"
    host: str = ""
    port: Any = 5432
    database: str = ""
    username: str = ""
    password: str = ""


class DetailsOut(BaseModel):
    tables: int
    rows: int


class DatabaseSourceOut(BaseModel):
    kind: str
    name: str
    host: str
    port: int
    database: str
    username: str
    status: str
    read_only_ok: bool
    data_through: datetime | None = None
    checked_at: datetime | None = None
    details: DetailsOut


class ConnectionTestOut(BaseModel):
    read_only_ok: bool
    data_through: None = None
    details: DetailsOut


def _bad_request(message: str) -> ApiError:
    return ApiError(400, "bad_request", message)


def check_input(body: DatabaseInput) -> tuple[str, int, str, str]:
    """The validated address, or a `bad_request` naming the bad field."""
    if body.kind != "postgres":
        raise _bad_request(f"Unknown database kind: `{body.kind}`.")
    if not body.host:
        raise _bad_request("`host` is missing.")
    if not body.database:
        raise _bad_request("`database` is missing.")
    if not body.username:
        raise _bad_request("`username` is missing.")
    port = body.port
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise _bad_request("`port` must be a whole number from 1 to 65535.")
    return body.host, port, body.database, body.username


def saved_source(session: Session) -> DataSource | None:
    """The newest saved connection, if any."""
    return session.scalar(select(DataSource).order_by(DataSource.id.desc()).limit(1))


def saved_password(session: Session) -> str:
    """The saved password, decrypted; empty when nothing is saved."""
    row = saved_source(session)
    if row is None:
        return ""
    return decrypt_text(row.password_encrypted)


def display_name(database: str) -> str:
    """`bella_forno` → "Bella Forno database" (P04.2's rule)."""
    words = [word.capitalize() for word in re.split(r"[_-]+", database) if word]
    return " ".join(words) + " database"


def check_source(host: str, port: int, database: str, username: str, password: str):
    """Connect, check read-only, summarise; failures raise, nothing is saved."""
    connector = PostgresConnector(host, port, database, username, password)
    if not connector.check_read_only():
        raise ConnectorError(
            "not_read_only", "This login can change data. Please use a read-only login."
        )
    return connector.summary()


def source_shape(row: DataSource) -> dict[str, Any]:
    """The `DatabaseSource` the screens expect; never the password."""
    return {
        "kind": row.kind,
        "name": row.name,
        "host": row.host,
        "port": row.port,
        "database": row.database,
        "username": row.username,
        "status": row.status,
        "read_only_ok": row.read_only_ok,
        "data_through": row.data_through,
        "checked_at": row.checked_at,
        "details": {
            "tables": row.details.get("tables", 0),
            "rows": row.details.get("rows", 0),
        },
    }


@sources_router.get("/api/sources/database", response_model=DatabaseSourceOut | None)
def get_database(session: Session = Depends(get_session)) -> dict[str, Any] | None:
    row = saved_source(session)
    return source_shape(row) if row is not None else None


@sources_router.post("/api/sources/database/test", response_model=ConnectionTestOut)
def test_database(body: DatabaseInput, session: Session = Depends(get_session)) -> dict[str, Any]:
    host, port, database, username = check_input(body)
    password = body.password or saved_password(session)
    if not password:
        raise ConnectorError("password_needed", "Please enter the password.")
    summary = check_source(host, port, database, username, password)
    return {
        "read_only_ok": True,
        "data_through": None,
        "details": {"tables": summary.tables, "rows": summary.rows},
    }


@sources_router.put("/api/sources/database", response_model=DatabaseSourceOut)
def put_database(body: DatabaseInput, session: Session = Depends(get_session)) -> dict[str, Any]:
    host, port, database, username = check_input(body)
    old = saved_source(session)
    password = body.password or (decrypt_text(old.password_encrypted) if old is not None else "")
    if not password:
        raise ConnectorError("password_needed", "Please enter the password.")
    summary = check_source(host, port, database, username, password)
    session.execute(delete(DataSource))
    row = DataSource(
        kind="postgres",
        name=display_name(database),
        host=host,
        port=port,
        database=database,
        username=username,
        password_encrypted=encrypt_text(password) if body.password else old.password_encrypted,  # type: ignore[union-attr]
        status="connected",
        read_only_ok=True,
        data_through=None,
        checked_at=datetime.now(UTC),
        details={
            "tables": summary.tables,
            "rows": summary.rows,
            "server_version": summary.server_version,
        },
    )
    session.add(row)
    session.commit()
    return source_shape(row)
