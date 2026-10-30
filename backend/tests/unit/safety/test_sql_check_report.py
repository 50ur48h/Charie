"""The report: every failure collected, plain words, normalised names."""

from charie.shared.safety.catalog import Catalog
from charie.shared.safety.sql_check import check_sql

CATALOG = Catalog(tables=["public.restaurants"])


def test_all_failures_collected() -> None:
    report = check_sql("DELETE FROM restaurants", CATALOG)
    assert report.ok is False
    assert report.rules == ["one_select"]
    assert len(report.reasons) == 2


def test_reasons_are_plain_english() -> None:
    queries = [
        "SELECT 'oops",
        "SELECT 1; SELECT 2",
        "DELETE FROM restaurants",
        "SELECT * FROM pg_class",
        "SELECT * FROM nope",
        "SELECT pg_sleep(1)",
        "SELECT frobnicate(id) FROM restaurants",
        "SELECT * FROM generate_series(1, 2)",
    ]
    for sql in queries:
        for reason in check_sql(sql, CATALOG).reasons:
            assert "exp." not in reason
            assert "sqlglot" not in reason.lower()


def test_table_names_normalised() -> None:
    report = check_sql("SELECT * FROM PUBLIC.Restaurants", CATALOG)
    assert report.ok is True
    assert report.tables == ["public.restaurants"]


def test_unreadable_names_sqlglot_reason() -> None:
    report = check_sql("FROM WHERE SELECT", CATALOG)
    assert report.ok is False
    assert report.rules == ["one_select"]
    assert report.reasons[0].startswith("Charie couldn't read this query: `")
