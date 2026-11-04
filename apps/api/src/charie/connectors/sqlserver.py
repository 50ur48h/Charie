"""The SQL Server connector (architecture Part 5.1, plan WP3.3)."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self, cast

import pyodbc

from charie.connectors import introspection
from charie.connectors.base import (
    Caps,
    ColumnInfo,
    ConnectorError,
    ExecLimits,
    ForeignKey,
    Health,
    ResultFrame,
    TableRef,
    TlsStatus,
    ValidatedQuery,
)
from charie.connectors.sanitizer import sanitize_exception
from charie.connectors.tls import odbc_parameters, tls_detail

__all__ = ["SQLSERVER_CAPS", "SqlServerConnector"]

#: pyodbc's objects carry partial annotations.
type OdbcConnection = Any

_connect: Any = pyodbc.connect

#: Installed by ``apps/api/docker/install-odbc.sh``.
ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

#: Shows up in sys.dm_exec_sessions, so a DBA can see who is asking.
APPLICATION_NAME = "charie"

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10

SQLSERVER_CAPS = Caps(
    dialect="tsql",
    max_identifier_length=128,
    # T-SQL's own spelling is [brackets].
    identifier_quote='"',
    catalog_access="sys",
    limit_syntax="top",
    statement_timeout_mechanism="driver_query_timeout",
    supports_tablesample=True,
    explain_format="showplan_xml",
)

#: SQLSTATE class 42 is "syntax error or access rule violation".
_ACCESS_RULE_VIOLATION = "42"


class SqlServerConnector:
    """One customer SQL Server database."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        tls_mode: str,
        connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host
        self._port = port
        self._database = database
        self._username = username
        self._password = password
        self._tls_mode = tls_mode
        self._connect_timeout = connect_timeout_seconds
        self._connection: OdbcConnection | None = None
        self._lock = asyncio.Lock()

    # -- lifecycle ---------------------------------------------------------

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            with suppress(Exception):
                await asyncio.to_thread(connection.close)

    def capabilities(self) -> Caps:
        return SQLSERVER_CAPS

    # -- connections -------------------------------------------------------

    def _known(self) -> tuple[str, ...]:
        """What must never appear in an error message leaving this class."""
        return (self._password, self._host, self._username, self._database)

    def _fail(self, error: Exception) -> ConnectorError:
        return ConnectorError(sanitize_exception(error, known=self._known()))

    async def _open(self, *, read_only: bool) -> OdbcConnection:
        try:
            return await asyncio.to_thread(self._connect_blocking, read_only=read_only)
        except Exception as error:
            raise self._fail(error) from None

    def _connect_blocking(self, *, read_only: bool) -> OdbcConnection:
        # Keyword form rather than a hand-built connection string.
        return _connect(
            driver=f"{{{ODBC_DRIVER}}}",
            server=f"{self._host},{self._port}",
            database=self._database,
            uid=self._username,
            pwd=self._password,
            app=APPLICATION_NAME,
            **odbc_parameters(self._tls_mode),
            # pyodbc's own keywords, not connection-string attributes.
            timeout=self._connect_timeout,
            autocommit=False,
            # Advisory on this driver, as the module docstring says.
            readonly=read_only,
        )

    async def _reader(self) -> OdbcConnection:
        if self._connection is None:
            self._connection = await self._open(read_only=True)
        return self._connection

    # -- the one execution path -------------------------------------------

    async def execute(self, query: ValidatedQuery, limits: ExecLimits) -> ResultFrame:
        """Run approved SQL. The only place this module sends a query."""
        connection = await self._reader()
        started = time.perf_counter()

        async with self._lock:
            try:
                columns, records = await asyncio.to_thread(
                    self._execute_blocking, connection, query, limits
                )
            except Exception as error:
                raise self._fail(error) from None

        duration_ms = int((time.perf_counter() - started) * 1000)
        truncated = len(records) > limits.max_rows
        rows = tuple(tuple(record) for record in records[: limits.max_rows])
        return ResultFrame(columns=columns, rows=rows, truncated=truncated, duration_ms=duration_ms)

    def _execute_blocking(
        self, connection: OdbcConnection, query: ValidatedQuery, limits: ExecLimits
    ) -> tuple[tuple[str, ...], list[tuple[object, ...]]]:
        connection.timeout = _query_timeout(limits)
        cursor = connection.cursor()
        try:
            cursor.execute(query.sql, *query.parameters)
            description = cast("Sequence[Sequence[object]] | None", cursor.description)
            if description is None:
                # A statement with no result set.
                return (), []
            columns = tuple(str(column[0]) for column in description)
            # One more than asked for, so "there was more" is a fact rather than a guess.
            fetched = cast("list[Sequence[object]]", cursor.fetchmany(limits.max_rows + 1))
            return columns, [tuple(row) for row in fetched]
        finally:
            with suppress(Exception):
                cursor.close()
            with suppress(Exception):
                connection.rollback()

    # -- introspection -----------------------------------------------------

    async def list_schemas(self) -> list[str]:
        frame = await self.execute(introspection.tsql_schemas(), _METADATA_LIMITS)
        return [str(row[0]) for row in frame.rows]

    async def list_tables(self, schemas: Sequence[str]) -> list[TableRef]:
        frame = await self.execute(introspection.tsql_tables(), _METADATA_LIMITS)
        wanted = set(schemas)
        return [
            TableRef(
                schema=str(row[0]),
                name=str(row[1]),
                kind=str(row[2]),
                comment=_optional(row[3]),
            )
            for row in frame.rows
            if str(row[0]) in wanted
        ]

    async def list_columns(self, schemas: Sequence[str]) -> list[ColumnInfo]:
        frame = await self.execute(introspection.tsql_columns(), _METADATA_LIMITS)
        wanted = set(schemas)
        return [
            ColumnInfo(
                schema=str(row[0]),
                table=str(row[1]),
                name=str(row[2]),
                data_type=str(row[3]),
                nullable=bool(row[4]),
                ordinal=int(cast("int", row[5])),
                is_primary_key=bool(row[6]),
                comment=_optional(row[7]),
            )
            for row in frame.rows
            if str(row[0]) in wanted
        ]

    async def list_foreign_keys(self, schemas: Sequence[str]) -> list[ForeignKey]:
        """One key per constraint, with its columns in key order."""
        frame = await self.execute(introspection.tsql_foreign_keys(), _METADATA_LIMITS)
        wanted = set(schemas)

        keys: dict[tuple[str, str, str], ForeignKey] = {}
        for row in frame.rows:
            constraint, from_schema, from_table = str(row[0]), str(row[1]), str(row[2])
            if from_schema not in wanted:
                continue
            identity = (from_schema, from_table, constraint)
            existing = keys.get(identity)
            if existing is None:
                keys[identity] = ForeignKey(
                    constraint_name=constraint,
                    from_schema=from_schema,
                    from_table=from_table,
                    from_columns=(str(row[3]),),
                    to_schema=str(row[4]),
                    to_table=str(row[5]),
                    to_columns=(str(row[6]),),
                )
            else:
                keys[identity] = ForeignKey(
                    constraint_name=existing.constraint_name,
                    from_schema=existing.from_schema,
                    from_table=existing.from_table,
                    from_columns=(*existing.from_columns, str(row[3])),
                    to_schema=existing.to_schema,
                    to_table=existing.to_table,
                    to_columns=(*existing.to_columns, str(row[6])),
                )
        return list(keys.values())

    # -- verification ------------------------------------------------------

    async def test_connection(self) -> Health:
        """Connect, then prove the credentials cannot write."""
        checked_at = datetime.now(UTC)

        try:
            await self.list_schemas()
        except ConnectorError as error:
            return Health(
                reachable=False,
                readonly_verified=False,
                detail=str(error),
                checked_at=checked_at,
            )

        tls = await self._tls_status()
        tls_note = () if tls is None else (f"TLS: {tls.detail}",)

        try:
            frame = await self.execute(introspection.tsql_readonly_evidence(), ExecLimits(1))
            facts = dict(zip(frame.columns, frame.rows[0], strict=True))
        except (ConnectorError, IndexError, ValueError) as error:
            return Health(
                reachable=True,
                readonly_verified=False,
                detail=(
                    "Connected, but could not establish whether these credentials "
                    f"are read-only: {error}"
                ),
                checked_at=checked_at,
                evidence=tls_note,
                tls=tls,
            )

        writable = _write_privileges(facts)
        probe_refused, probe_note = await self._write_probe()
        evidence = (*tls_note, *writable, probe_note)

        verified = not writable and probe_refused
        detail = (
            "Connected. These credentials cannot write."
            if verified
            else "Connected, but these credentials are not read-only: "
            + "; ".join(writable or (probe_note,))
        )

        return Health(
            reachable=True,
            readonly_verified=verified,
            detail=detail,
            checked_at=checked_at,
            server_version=_version(facts),
            evidence=evidence,
            tls=tls,
        )

    async def _tls_status(self) -> TlsStatus | None:
        """Whether this session is encrypted — from the server if it will say."""
        try:
            frame = await self.execute(introspection.tsql_tls_status(), ExecLimits(1))
            option = str(frame.rows[0][0]).upper()
        except (ConnectorError, IndexError):
            return self._tls_from_driver()

        encrypted = option == "TRUE"
        return TlsStatus(
            mode=self._tls_mode,
            encrypted=encrypted,
            detail=tls_detail(mode=self._tls_mode, encrypted=encrypted),
        )

    def _tls_from_driver(self) -> TlsStatus:
        encrypted = self._tls_mode != "disable"
        return TlsStatus(
            mode=self._tls_mode,
            encrypted=encrypted,
            detail=(
                f"{tls_detail(mode=self._tls_mode, encrypted=encrypted)} "
                "(according to the driver: this login may not read the server's "
                "own view of the connection)"
            ),
        )

    async def _write_probe(self) -> tuple[bool, str]:
        """Attempt one write on a connection that is not declared read-only."""
        try:
            connection = await self._open(read_only=False)
        except ConnectorError as error:
            return False, f"the write probe could not run ({error})"

        try:
            return await asyncio.to_thread(self._probe_blocking, connection)
        except Exception as error:
            return False, f"the write probe could not run ({self._fail(error)})"
        finally:
            with suppress(Exception):
                await asyncio.to_thread(connection.close)

    def _probe_blocking(self, connection: OdbcConnection) -> tuple[bool, str]:
        cursor = connection.cursor()
        try:
            cursor.execute(introspection.tsql_write_probe_sql())
        except pyodbc.Error as error:
            state = _sqlstate(error)
            if state.startswith(_ACCESS_RULE_VIOLATION):
                return True, f"CREATE TABLE was refused (SQLSTATE {state})"
            # A link failure is not a refusal.
            return False, f"the write probe could not run (SQLSTATE {state})"
        else:
            return False, (
                "CREATE TABLE succeeded and was rolled back — these credentials can write"
            )
        finally:
            with suppress(Exception):
                cursor.close()
            with suppress(Exception):
                connection.rollback()


#: Metadata results are bounded by the size of the customer's schema, not by their data.
_METADATA_LIMITS = ExecLimits(max_rows=50_000, timeout_seconds=30.0)


def _query_timeout(limits: ExecLimits) -> int:
    """ODBC counts whole seconds, and zero means "no limit" — never that."""
    return max(1, math.ceil(limits.timeout_seconds))


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def _write_privileges(facts: dict[str, object]) -> tuple[str, ...]:
    """Everything the catalog says this login may do that a reader may not."""
    findings: list[str] = []

    if _flag(facts, "is_sysadmin"):
        findings.append("the login is a member of the sysadmin server role")
    if _flag(facts, "is_db_owner"):
        findings.append("the login is a member of db_owner")
    if _flag(facts, "is_db_datawriter"):
        findings.append("the login is a member of db_datawriter")
    if _flag(facts, "is_ddladmin"):
        findings.append("the login is a member of db_ddladmin")
    if _flag(facts, "can_create_in_database"):
        findings.append("the login may create tables in this database")

    tables = _count(facts, "writable_tables")
    if tables:
        findings.append(f"{tables} table(s) accept INSERT, UPDATE, DELETE or ALTER from this login")

    return tuple(findings)


def _flag(facts: dict[str, object], name: str) -> bool:
    """T-SQL has no boolean type: these arrive as 1 or 0."""
    value = facts.get(name)
    if isinstance(value, bool):
        return value
    return isinstance(value, int) and value == 1


def _count(facts: dict[str, object], name: str) -> int:
    value = facts.get(name)
    return value if isinstance(value, int) else 0


def _version(facts: dict[str, object]) -> str | None:
    """Assembled, not taken from @@VERSION, which also names the host OS."""
    raw = facts.get("product_version")
    return f"Microsoft SQL Server {raw}" if isinstance(raw, str) else None


def _sqlstate(error: pyodbc.Error) -> str:
    args = cast("tuple[object, ...]", error.args)
    return str(args[0]) if args else "unknown"
