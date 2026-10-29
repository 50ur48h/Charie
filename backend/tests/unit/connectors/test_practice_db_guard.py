"""Unmarked tests can't reach the practice database."""

import pytest

from charie.shared.config import get_settings
from charie.shared.connectors.base import PracticeDbBlocked
from charie.shared.connectors.postgres import PostgresConnector


def test_unmarked_test_blocked_before_connecting(monkeypatch) -> None:
    monkeypatch.setenv("PRACTICE_DB_URL", "postgresql://reader:pw@127.0.0.1:5432/practice")
    get_settings.cache_clear()
    connector = PostgresConnector("localhost", 5432, "practice", "reader", "pw")
    with pytest.raises(PracticeDbBlocked, match="practice database"):
        connector._connect()
