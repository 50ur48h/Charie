"""Postgres, the only customer database today: read-only, timed, limited."""

import time
from urllib.parse import urlparse

import psycopg

from charie.shared.connectors.base import (
    ConnectorError,
    DbSummary,
    QueryBlocked,
    QueryResult,
)

_USER_TABLES = "c.relkind IN ('r', 'v', 'm')"
_SYSTEM_SCHEMAS = "n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')"


def _cant_connect(message: str) -> ConnectorError:
    return ConnectorError("cant_connect", message)


def _code(error: BaseException) -> ConnectorError:
    """Turn a driver error into the one plain-English refusal."""
    text = str(error).split("\n")[0]
    state = getattr(error, "sqlstate", None)
    if state == "28P01" or "password authentication failed" in text:
        return ConnectorError("login_failed", "The username or password is wrong.")
    lowered = text.lower()
    if any(
        piece in lowered
        for piece in (
            "could not connect",
            "connection refused",
            "no such host",
            "name or service not known",
            "timeout expired",
            "connection timed out",
        )
    ):
        return ConnectorError(
            "cant_connect",
            "Charie couldn't reach this server. Check the server address and port.",
        )
    if "does not exist" in text and "database" in text:
        name = text.split('database "', 1)[1].split('"', 1)[0] if 'database "' in text else ""
        if name:
            return ConnectorError(
                "cant_connect", f"There's no database called `{name}` on that server."
            )
    if state == "57014" or "canceling statement due to statement timeout" in text:
        return ConnectorError(
            "query_timeout", "The query took longer than 60 seconds, so it was stopped."
        )
    if state == "25006" or "read-only transaction" in text:
        return ConnectorError(
            "write_refused", "Charie only reads data, and this query tried to change something."
        )
    return _cant_connect(f"Charie couldn't connect: `{text}`.")


class PostgresConnector:
    """One customer's Postgres, reached read-only or not at all."""

    def __init__(self, host: str, port: int, database: str, username: str, password: str) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password

    @classmethod
    def from_url(cls, url: str) -> "PostgresConnector":
        """A connector from a Postgres URL (used for `PRACTICE_DB_URL`)."""
        parts = urlparse(url)
        if not parts.hostname or not parts.path.lstrip("/"):
            raise ValueError(f"Not a Postgres URL: `{url}`.")
        return cls(
            host=parts.hostname,
            port=parts.port or 5432,
            database=parts.path.lstrip("/"),
            username=(parts.username or ""),
            password=(parts.password or ""),
        )

    def _connect(self):
        """A fresh connection. The test guard watches this method."""
        try:
            return psycopg.connect(
                host=self.host,
                port=self.port,
                dbname=self.database,
                user=self.username,
                password=self.password,
                connect_timeout=10,
            )
        except psycopg.OperationalError as err:
            raise _code(err) from err

    def check_read_only(self) -> bool:
        """True when the login can read but never change data."""
        try:
            with self._connect() as conn:
                if conn.execute(
                    "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
                ).fetchone()[0]:
                    return False
                changed = conn.execute(
                    f"""SELECT EXISTS (
                        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE {_USER_TABLES} AND {_SYSTEM_SCHEMAS}
                        AND (has_table_privilege(c.oid, 'INSERT')
                            OR has_table_privilege(c.oid, 'UPDATE')
                            OR has_table_privilege(c.oid, 'DELETE')
                            OR has_table_privilege(c.oid, 'TRUNCATE'))
                    )"""
                ).fetchone()[0]
                return not changed
        except psycopg.Error as err:
            raise _code(err) from err

    def summary(self) -> DbSummary:
        """Tables, rows and the server version, for the Sources card."""
        try:
            with self._connect() as conn:
                tables = conn.execute(
                    f"""SELECT count(*) FROM pg_class c JOIN pg_namespace n
                        ON n.oid = c.relnamespace
                        WHERE {_USER_TABLES} AND {_SYSTEM_SCHEMAS}"""
                ).fetchone()[0]
                rows = conn.execute(
                    f"""SELECT coalesce(sum(greatest(c.reltuples, 0)), 0)
                        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relkind = 'r' AND {_SYSTEM_SCHEMAS}"""
                ).fetchone()[0]
                version = conn.execute("SHOW server_version").fetchone()[0]
        except psycopg.Error as err:
            raise _code(err) from err
        return DbSummary(tables=int(tables), rows=int(rows), server_version=str(version))

    def run_checked(self, sql: str, catalog, max_rows: int = 50_000) -> QueryResult:
        """Check first with the safety checker; a blocked query never runs."""
        from charie.shared.safety.sql_check import check_sql

        report = check_sql(sql, catalog, max_rows=max_rows)
        if not report.ok:
            raise QueryBlocked(report.reasons)
        return self.run_query(report.sql, max_rows=max_rows)

    def run_query(self, query: str, timeout_s: int = 60, max_rows: int = 50_000) -> QueryResult:
        """Run one SELECT read-only, timed and capped; then roll back."""
        try:
            with self._connect() as conn:
                conn.read_only = True
                started = time.monotonic()
                with conn.cursor() as cur:
                    cur.execute(f"SET LOCAL statement_timeout = {int(timeout_s) * 1000}")
                    cur.execute(query)
                    columns = [field.name for field in cur.description or []]
                    fetched = cur.fetchmany(max_rows + 1)
                conn.rollback()
        except psycopg.Error as err:
            raise _code(err) from err
        if len(fetched) > max_rows:
            raise ConnectorError(
                "too_many_rows",
                "The query returned more than 50,000 rows, so it was stopped. "
                "Ask a more focused question.",
            )
        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        return QueryResult(
            columns=columns,
            rows=[list(row) for row in fetched],
            row_count=len(fetched),
            duration_ms=duration_ms,
        )
