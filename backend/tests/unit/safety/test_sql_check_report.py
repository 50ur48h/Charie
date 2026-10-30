"""The report: every failure collected, plain words, normalised names."""

from charie.shared.safety.catalog import Catalog, Link, RequiredFilter
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


def test_double_counting_names_tables() -> None:
    report = check_sql(
        "SELECT SUM(o.total) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE o.status = 'completed'",
        Catalog(
            tables=["public.orders", "public.order_items"],
            required_filters=[
                RequiredFilter(
                    table="public.orders",
                    sql="orders.status = 'completed'",
                    reason="completed orders only",
                )
            ],
            links=[
                Link(
                    one_table="public.orders",
                    one_column="id",
                    many_table="public.order_items",
                    many_column="order_id",
                )
            ],
        ),
    )
    assert report.rules == ["double_counting"]
    assert report.reasons == [
        "This query adds up `public.orders.total` after joining `public.order_items`, "
        "which has many rows for each `public.orders` row. Each `public.orders` row "
        "would be counted once per `public.order_items` row. Add up "
        "`public.order_items` first in a sub-query, or don't join it."
    ]


def test_count_star_with_join_is_allowed() -> None:
    report = check_sql(
        "SELECT COUNT(*) FROM restaurants r JOIN orders o ON o.id = r.id "
        "WHERE o.status = 'completed'",
        CATALOG,
    )
    assert report.ok is True


def test_avg_plain_column_is_allowed() -> None:
    report = check_sql("SELECT AVG(total) FROM restaurants", CATALOG)
    assert report.ok is True
