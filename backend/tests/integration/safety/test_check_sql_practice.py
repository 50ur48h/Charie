"""Rule 7 on the real practice database (read-only): heavy is blocked, normal runs."""

import pytest

from charie.shared.config import require_env
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.safety import check_sql_cli
from charie.shared.safety.list_tables import list_tables


def _practice() -> PostgresConnector:
    return PostgresConnector.from_url(require_env("PRACTICE_DB_URL"))


@pytest.mark.practice_db
def test_cross_join_is_too_heavy(capsys) -> None:
    code = check_sql_cli.run(
        ["SELECT * FROM public.orders CROSS JOIN public.order_items"],
    )
    assert code == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("Mode: no knowledge yet.")
    assert "Blocked:" in out
    assert "too heavy to run safely" in out


@pytest.mark.practice_db
def test_normal_aggregate_allowed_and_counted(capsys) -> None:
    names = list_tables(_practice())
    table = sorted(names)[0]
    code = check_sql_cli.run([f"SELECT COUNT(*) FROM {table}", "--count"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Allowed." in out
    assert "It returns 1 rows on the practice database." in out


@pytest.mark.practice_db
def test_list_tables_finds_57() -> None:
    names = list_tables(_practice())
    assert len(names) == 57
    assert len(set(names)) == 57
    assert all("." in name and " " not in name for name in names)
