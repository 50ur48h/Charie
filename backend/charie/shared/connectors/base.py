"""Connector shapes and errors. Every query runs read-only (06)."""

from dataclasses import dataclass, field

from charie.shared.errors import ApiError


@dataclass
class QueryResult:
    """What one read-only query returned."""

    columns: list[str]
    rows: list[list[object]]
    row_count: int
    duration_ms: int
    tables: list[str] = field(default_factory=list)


@dataclass
class DbSummary:
    """Tables, rows and the server version, for the Sources card."""

    tables: int
    rows: int
    server_version: str


class ConnectorError(ApiError):
    """The database refused, in plain words (always HTTP 400)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(400, code, message)


class QueryBlocked(ConnectorError):
    """The safety checker refused a query, with every reason listed."""

    def __init__(self, reasons: list) -> None:
        super().__init__(
            "query_blocked",
            "Charie can't run this query. " + " ".join(str(reason) for reason in reasons),
        )
        self.reasons = list(reasons)


class PracticeDbBlocked(Exception):
    """A test tried to reach the practice database without the mark."""

    def __init__(self) -> None:
        super().__init__(
            "This test tried to reach the practice database. Mark it with @pytest.mark.practice_db."
        )
