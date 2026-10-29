"""The real practice database (laptop only, read-only, never written)."""

import pytest

from charie.shared.config import require_env
from charie.shared.connectors.postgres import PostgresConnector

pytestmark = pytest.mark.practice_db


def _practice() -> PostgresConnector:
    return PostgresConnector.from_url(require_env("PRACTICE_DB_URL"))


def test_charie_readonly_passes() -> None:
    connector = _practice()
    assert connector.check_read_only() is True
    summary = connector.summary()
    assert summary.tables == 57
    assert summary.rows > 0


def test_practice_query_reads_rows() -> None:
    result = _practice().run_query(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1 LIMIT 5"
    )
    assert result.row_count > 0 and result.duration_ms >= 0
