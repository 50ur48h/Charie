"""What every connector is, and what may reach one (architecture Part 5.1)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, final, runtime_checkable

__all__ = [
    "SANCTIONED_VALIDATORS",
    "Caps",
    "ColumnInfo",
    "Connector",
    "ConnectorError",
    "ExecLimits",
    "ForeignKey",
    "Health",
    "PolicyGrant",
    "ResultFrame",
    "TableRef",
    "TlsStatus",
    "ValidatedQuery",
]

#: The only modules that may declare SQL fit to run.
SANCTIONED_VALIDATORS: frozenset[str] = frozenset(
    {
        # Fixed templates with bound parameters, no user input anywhere near them.
        "charie.connectors.introspection",
        # Phase 5. Named now so the shape of the list is visible from the start.
        "charie.dal.validator",
    }
)


class ConnectorError(Exception):
    """A failure talking to a customer database, already sanitized."""

    def __init__(self, message: str, *, statement_fault: bool = False) -> None:
        super().__init__(message)
        self.statement_fault = statement_fault


@final
class PolicyGrant:
    """The right to declare a piece of SQL validated."""

    __slots__ = ("holder",)

    def __init__(self, holder: str) -> None:
        if holder not in SANCTIONED_VALIDATORS:
            raise PermissionError(
                f"{holder!r} may not declare SQL validated. Only the SQL policy "
                "module may build a ValidatedQuery (architecture Part 5.1, 7.5)."
            )
        self.holder = holder


@final
class ValidatedQuery:
    """SQL that a sanctioned validator has approved, plus its bound parameters."""

    __slots__ = ("_dialect", "_origin", "_parameters", "_sql")

    def __init__(
        self,
        grant: PolicyGrant,
        *,
        sql: str,
        dialect: str,
        parameters: Sequence[object] = (),
    ) -> None:
        # The annotation says PolicyGrant; this is the runtime half of the same statement.
        if not isinstance(grant, PolicyGrant):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("A ValidatedQuery needs a PolicyGrant from the SQL policy module.")
        self._sql = sql
        self._dialect = dialect
        self._parameters = tuple(parameters)
        self._origin = grant.holder

    @property
    def sql(self) -> str:
        return self._sql

    @property
    def dialect(self) -> str:
        return self._dialect

    @property
    def parameters(self) -> tuple[object, ...]:
        return self._parameters

    @property
    def origin(self) -> str:
        """Which validator approved this. Recorded with executions from Phase 5."""
        return self._origin

    @property
    def sql_hash(self) -> str:
        return hashlib.sha256(self._sql.encode()).hexdigest()[:12]

    def __repr__(self) -> str:
        return (
            f"ValidatedQuery(dialect={self._dialect!r}, origin={self._origin!r}, "
            f"sql_hash={self.sql_hash!r})"
        )


@dataclass(frozen=True, slots=True)
class Caps:
    """Per-engine truth, stated rather than inferred (architecture Part 5.1)."""

    #: sqlglot's name for this dialect: postgres | tsql | mysql.
    dialect: str
    max_identifier_length: int
    identifier_quote: str
    #: information_schema | sys — where metadata comes from.
    catalog_access: str
    #: limit | top — consumed by the DAL's transpile step in Phase 5.
    limit_syntax: str
    #: How a per-statement deadline is imposed: a session GUC, or a driver option.
    statement_timeout_mechanism: str
    supports_tablesample: bool
    explain_format: str


@dataclass(frozen=True, slots=True)
class TlsStatus:
    """What was asked for, and what the server says actually happened."""

    #: The policy this connection was opened with.
    mode: str
    #: Not our opinion — read back from the engine's own view of this session.
    encrypted: bool
    #: One line, safe to show: protocol and cipher, and what was *not* checked.
    detail: str


@dataclass(frozen=True, slots=True)
class Health:
    """The answer to "can we use this data source, and is it safe to?"."""

    reachable: bool
    readonly_verified: bool
    detail: str
    checked_at: datetime
    server_version: str | None = None
    #: Each check that ran, and what it found.
    evidence: tuple[str, ...] = ()
    #: None when the check never got far enough to know.
    tls: TlsStatus | None = None


@dataclass(frozen=True, slots=True)
class TableRef:
    schema: str
    name: str
    #: table | view
    kind: str
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    schema: str
    table: str
    name: str
    data_type: str
    nullable: bool
    ordinal: int
    is_primary_key: bool
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class ForeignKey:
    constraint_name: str
    from_schema: str
    from_table: str
    from_columns: tuple[str, ...]
    to_schema: str
    to_table: str
    to_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecLimits:
    """Every execution is bounded. There is no unbounded variant to reach for."""

    max_rows: int = 1000
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class ResultFrame:
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    #: True when ``max_rows`` cut the result short.
    truncated: bool
    duration_ms: int


@runtime_checkable
class Connector(Protocol):
    """One database, spoken to in one shape."""

    def capabilities(self) -> Caps: ...

    async def aclose(self) -> None:
        """Release the connection. Every caller owes a connector this."""
        ...

    async def test_connection(self) -> Health: ...

    async def list_schemas(self) -> list[str]: ...

    async def list_tables(self, schemas: Sequence[str]) -> list[TableRef]: ...

    async def list_columns(self, schemas: Sequence[str]) -> list[ColumnInfo]: ...

    async def list_foreign_keys(self, schemas: Sequence[str]) -> list[ForeignKey]: ...

    async def execute(self, query: ValidatedQuery, limits: ExecLimits) -> ResultFrame: ...
