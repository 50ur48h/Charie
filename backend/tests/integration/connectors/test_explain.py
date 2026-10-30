"""EXPLAIN plans a query without running it (rule 7 needs the Total Cost)."""

import time
from urllib.parse import urlparse

from charie.shared.connectors.postgres import PostgresConnector


def test_explain_does_not_run_the_query(db) -> None:
    parts = urlparse(db)
    connector = PostgresConnector(
        host=parts.hostname or "localhost",
        port=parts.port or 5432,
        database=parts.path.lstrip("/"),
        username=parts.username or "",
        password=parts.password or "",
    )
    started = time.monotonic()
    plan = connector.explain("SELECT pg_sleep(5)")
    assert time.monotonic() - started < 1
    assert plan[0]["Plan"]["Total Cost"] >= 0
