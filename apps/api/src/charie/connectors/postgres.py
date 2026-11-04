"""The PostgreSQL connector (architecture Part 5.1, plan WP3.2)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self, cast

import asyncpg

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
from charie.connectors.tls import ssl_parameter, tls_detail

__all__ = ["POSTGRES_CAPS", "PostgresConnector"]

#: asyncpg's own objects, deliberately untyped here — see the module note.
type AsyncpgConnection = Any

#: Bound through an Any-typed name for the same reason, and this is the one suppression in the file.
_connect: Any = asyncpg.connect  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

#: Shows up in pg_stat_activity, so a DBA can see who is asking.
APPLICATION_NAME = "charie"

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0

POSTGRES_CAPS = Caps(
    dialect="postgres",
    max_identifier_length=63,
    identifier_quote='"',
    catalog_access="pg_catalog",
    limit_syntax="limit",
    statement_timeout_mechanism="set_statement_timeout",
    supports_tablesample=True,
    explain_format="json",
)


class PostgresConnector:
    """One customer PostgreSQL database."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        tls_mode: str,
        tls_ca_file: Path | None = None,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host
        self._port = port
        self._database = database
        self._username = username
        self._password = password
        # Required, with no default: how much encryption a customer's credentials travel under...
        self._tls_mode = tls_mode
        self._tls_ca_file = tls_ca_file
        self._connect_timeout = connect_timeout_seconds
        self._connection: AsyncpgConnection | None = None

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
                await connection.close()

    def capabilities(self) -> Caps:
        return POSTGRES_CAPS

    # -- connections -------------------------------------------------------

    def _known(self) -> tuple[str, ...]:
        """What must never appear in an error message leaving this class."""
        return (self._password, self._host, self._username, self._database)

    def _fail(self, error: Exception) -> ConnectorError:
        return ConnectorError(
            sanitize_exception(error, known=self._known()),
            statement_fault=_statement_fault(error),
        )

    async def _open(self, *, read_only: bool) -> AsyncpgConnection:
        settings = {"application_name": APPLICATION_NAME}
        if read_only:
            settings["default_transaction_read_only"] = "on"

        try:
            return await _connect(
                host=self._host,
                port=self._port,
                user=self._username,
                password=self._password,
                database=self._database,
                timeout=self._connect_timeout,
                server_settings=settings,
                # Whatever the policy decided for this data source.
                ssl=ssl_parameter(self._tls_mode, self._tls_ca_file),
            )
        except Exception as error:
            raise self._fail(error) from None

    async def _reader(self) -> AsyncpgConnection:
        if self._connection is None or self._connection.is_closed():
            self._connection = await self._open(read_only=True)
        return self._connection

    # -- the one execution path -------------------------------------------

    async def execute(self, query: ValidatedQuery, limits: ExecLimits) -> ResultFrame:
        """Run approved SQL. The only place this module sends a query."""
        connection = await self._reader()
        started = time.perf_counter()

        try:
            async with connection.transaction(readonly=True):
                # SET LOCAL: bounded by this transaction.
                await connection.execute(_statement_timeout(limits))
                statement = await connection.prepare(query.sql)
                columns = tuple(str(attribute.name) for attribute in statement.get_attributes())
                cursor = await statement.cursor(*query.parameters)
                records = await cursor.fetch(limits.max_rows + 1)
        except Exception as error:
            raise self._fail(error) from None

        duration_ms = int((time.perf_counter() - started) * 1000)
        truncated = len(records) > limits.max_rows
        rows = tuple(tuple(record.values()) for record in records[: limits.max_rows])
        return ResultFrame(columns=columns, rows=rows, truncated=truncated, duration_ms=duration_ms)

    # -- introspection -----------------------------------------------------

    async def list_schemas(self) -> list[str]:
        frame = await self.execute(introspection.pg_schemas(), _METADATA_LIMITS)
        return [str(row[0]) for row in frame.rows]

    async def list_tables(self, schemas: Sequence[str]) -> list[TableRef]:
        frame = await self.execute(introspection.pg_tables(schemas), _METADATA_LIMITS)
        return [
            TableRef(
                schema=str(row[0]),
                name=str(row[1]),
                kind=str(row[2]),
                comment=_optional(row[3]),
            )
            for row in frame.rows
        ]

    async def list_columns(self, schemas: Sequence[str]) -> list[ColumnInfo]:
        frame = await self.execute(introspection.pg_columns(schemas), _METADATA_LIMITS)
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
        ]

    async def list_foreign_keys(self, schemas: Sequence[str]) -> list[ForeignKey]:
        frame = await self.execute(introspection.pg_foreign_keys(schemas), _METADATA_LIMITS)
        return [
            ForeignKey(
                constraint_name=str(row[0]),
                from_schema=str(row[1]),
                from_table=str(row[2]),
                from_columns=_names(row[3]),
                to_schema=str(row[4]),
                to_table=str(row[5]),
                to_columns=_names(row[6]),
            )
            for row in frame.rows
        ]

    # -- verification ------------------------------------------------------

    async def test_connection(self) -> Health:
        """Connect, then prove the credentials cannot write."""
        checked_at = datetime.now(UTC)

        try:
            schemas = await self.list_schemas()
        except ConnectorError as error:
            return Health(
                reachable=False,
                readonly_verified=False,
                detail=str(error),
                checked_at=checked_at,
            )

        # Asked before the privilege questions.
        tls = await self._tls_status()
        tls_note = () if tls is None else (f"TLS: {tls.detail}",)

        try:
            frame = await self.execute(introspection.pg_readonly_evidence(schemas), ExecLimits(1))
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
        evidence = (*tls_note, *writable, probe_note, *self._role_note(facts))

        verified = not writable and probe_refused
        # The role's name is not repeated back.
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
        """Whether this session is encrypted, according to the server (B-013)."""
        try:
            frame = await self.execute(introspection.pg_tls_status(), ExecLimits(1))
            facts = dict(zip(frame.columns, frame.rows[0], strict=True))
        except (ConnectorError, IndexError, ValueError):
            return None

        encrypted = facts.get("encrypted") is True
        return TlsStatus(
            mode=self._tls_mode,
            encrypted=encrypted,
            detail=tls_detail(
                mode=self._tls_mode,
                encrypted=encrypted,
                version=_optional(facts.get("tls_version")),
                cipher=_optional(facts.get("cipher")),
            ),
        )

    def _role_note(self, facts: dict[str, object]) -> tuple[str, ...]:
        """Say that the server disagrees about who connected, never who."""
        reported = facts.get("role_name")
        if isinstance(reported, str) and reported != self._username:
            return ("the server reports a different role than the one configured",)
        return ()

    async def _write_probe(self) -> tuple[bool, str]:
        """Attempt one write, on a connection that is not read-only."""
        try:
            connection = await self._open(read_only=False)
        except ConnectorError as error:
            return False, f"the write probe could not run ({error})"

        try:
            transaction = connection.transaction()
            await transaction.start()
            try:
                await connection.execute(introspection.pg_write_probe_sql())
            except asyncpg.InsufficientPrivilegeError:
                return True, "CREATE TABLE was refused: permission denied"
            except asyncpg.PostgresError as error:
                # Any other refusal — no schema it may create in, for instance — is still a refusal.
                return True, f"CREATE TABLE was refused (SQLSTATE {_sqlstate(error)})"
            else:
                return False, (
                    "CREATE TABLE succeeded and was rolled back — these credentials can write"
                )
            finally:
                with suppress(Exception):
                    await transaction.rollback()
        except Exception as error:
            return False, f"the write probe could not run ({self._fail(error)})"
        finally:
            with suppress(Exception):
                await connection.close()


#: Metadata results are bounded by the size of the customer's schema, not by their data.
_METADATA_LIMITS = ExecLimits(max_rows=50_000, timeout_seconds=30.0)


def _statement_timeout(limits: ExecLimits) -> str:
    """``SET LOCAL`` cannot take a bind parameter; this takes no input either."""
    return f"SET LOCAL statement_timeout = {max(1, int(limits.timeout_seconds * 1000))}"


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def _names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in cast("Sequence[object]", value))


def _write_privileges(facts: dict[str, object]) -> tuple[str, ...]:
    """Everything the catalog says this role may do that a reader may not."""
    findings: list[str] = []

    if _flag(facts, "is_superuser"):
        findings.append("the role is a superuser")
    if _flag(facts, "can_bypass_rls"):
        findings.append("the role can bypass row-level security")
    if _flag(facts, "writes_everything"):
        findings.append("the role is a member of pg_write_all_data")
    if _flag(facts, "can_create_in_database"):
        findings.append("the role may create objects in this database")

    schemas = _count(facts, "writable_schemas")
    if schemas:
        findings.append(f"{schemas} schema(s) allow this role to create objects")

    tables = _count(facts, "writable_tables")
    if tables:
        findings.append(
            f"{tables} table(s) accept INSERT, UPDATE, DELETE or TRUNCATE from this role"
        )

    return tuple(findings)


def _flag(facts: dict[str, object], name: str) -> bool:
    return facts.get(name) is True


def _count(facts: dict[str, object], name: str) -> int:
    value = facts.get(name)
    return value if isinstance(value, int) else 0


def _version(facts: dict[str, object]) -> str | None:
    raw = facts.get("server_version")
    if not isinstance(raw, str):
        return None
    # "PostgreSQL 16.4 (Debian …) on x86_64…" — the first two words are the part anyone reads.
    return " ".join(raw.split()[:2])


#: SQLSTATE classes where the statement was rejected rather than the connection lost.
_STATEMENT_FAULT_CLASSES: Final = ("42", "22")

#: Inside ``42`` and deliberately excluded.
_NOT_A_REWRITE: Final = frozenset({"42501"})


def _statement_fault(error: Exception) -> bool:
    """Whether rewriting the SQL could plausibly fix this."""
    if not isinstance(error, asyncpg.PostgresError):
        return False
    state = _sqlstate(error)
    return state[:2] in _STATEMENT_FAULT_CLASSES and state not in _NOT_A_REWRITE


def _sqlstate(error: asyncpg.PostgresError) -> str:
    return str(getattr(error, "sqlstate", "unknown"))
