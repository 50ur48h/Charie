"""The report: every failure collected, plain words, normalised names."""

from charie.shared.safety.catalog import Catalog, RequiredFilter
from charie.shared.safety.sql_check import check_sql

CATALOG = Catalog(
    tables=["public.orders", "public.order_items", "public.restaurants"],
    required_filters=[
        RequiredFilter(
            table="public.orders",
            sql="orders.status = 'completed'",
            reason="completed orders only",
        )
    ],
    average_columns=["avg_revenue"],
)


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
    report = check_sql("SELECT id FROM PUBLIC.Restaurants", CATALOG)
    assert report.ok is True
    assert report.tables == ["public.restaurants"]


def test_unreadable_names_sqlglot_reason() -> None:
    report = check_sql("FROM WHERE SELECT", CATALOG)
    assert report.ok is False
    assert report.rules == ["one_select"]
    assert report.reasons[0].startswith("Charie couldn't read this query: `")


def test_avg_message_names_first_listed_column() -> None:
    report = check_sql("SELECT AVG(total) FROM restaurants", CATALOG)
    assert report.rules == ["averaging"]
    assert report.reasons == [
        "`AVG` only makes sense over `avg_revenue`: use one of Charie's "
        "pre-computed averages instead."
    ]


def test_count_message() -> None:
    report = check_sql(
        "SELECT COUNT(*) FROM restaurants r JOIN orders o ON o.id = r.id "
        "WHERE o.status = 'completed'",
        CATALOG,
    )
    assert report.rules == ["counting"]
    assert report.reasons == [
        "`COUNT` counts rows; counts over one table at once only make sense in a learning run."
    ]


def test_star_message() -> None:
    report = check_sql("SELECT * FROM restaurants", CATALOG)
    assert report.rules == ["explicit-columns"]
    assert report.reasons == [
        "This query would read a whole `public.restaurants` row: name the "
        "columns it needs. (Rule: explicit-columns)"
    ]
