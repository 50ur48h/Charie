"""Rule 1-6 cases: one table of (id, sql, ok, rule)."""

import pytest

from charie.shared.safety.catalog import Catalog, Link, RequiredFilter
from charie.shared.safety.sql_check import check_sql

CATALOG = Catalog(
    tables=[
        "public.orders",
        "public.order_items",
        "public.order_refunds",
        "public.restaurants",
    ],
    forbidden_tables=["public.orders_old"],
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
        ),
        Link(
            one_table="public.order_items",
            one_column="id",
            many_table="public.order_refunds",
            many_column="item_id",
        ),
    ],
    average_columns=["avg_revenue"],
)

# (id, sql, ok, rule or None).
CASES = [
    ("plain_aggregate", "SELECT COUNT(*) FROM restaurants", True, None),
    ("with_select", "WITH x AS (SELECT id FROM restaurants) SELECT id FROM x", True, None),
    ("two_statements", "SELECT 1; SELECT 2", False, "one_select"),
    ("delete", "DELETE FROM orders WHERE id = 1", False, "one_select"),
    (
        "delete_in_with",
        "WITH x AS (DELETE FROM orders RETURNING id) SELECT id FROM x",
        False,
        "one_select",
    ),
    ("select_into", "SELECT id INTO t2 FROM restaurants", False, "one_select"),
    ("for_update", "SELECT id FROM restaurants FOR UPDATE", False, "one_select"),
    ("for_share", "SELECT id FROM restaurants FOR SHARE", False, "one_select"),
    ("call", "CALL refresh_orders()", False, "one_select"),
    ("lock_table", "LOCK TABLE restaurants", False, "one_select"),
    ("pg_class", "SELECT id FROM pg_class", False, "allowed_tables"),
    (
        "information_schema",
        "SELECT table_name FROM information_schema.tables",
        False,
        "allowed_tables",
    ),
    ("unknown_table", "SELECT id FROM foo", False, "allowed_tables"),
    ("forbidden_table", "SELECT id FROM orders_old", False, "allowed_tables"),
    ("pg_sleep", "SELECT pg_sleep(5)", False, "functions"),
    ("dblink", "SELECT dblink('x', 'SELECT 1')", False, "functions"),
    ("unknown_function", "SELECT frobnicate(id) FROM restaurants", False, "functions"),
    (
        "generate_series",
        "SELECT id FROM generate_series(1, 10)",
        False,
        "allowed_tables",
    ),
    ("missing_filter", "SELECT id FROM orders", False, "required_filters"),
    (
        "filter_with_alias",
        "SELECT o.id FROM orders o WHERE o.status = 'completed'",
        True,
        None,
    ),
    (
        "filter_no_prefix_single_table",
        "SELECT id FROM orders WHERE status = 'completed'",
        True,
        None,
    ),
    (
        "filter_inside_or",
        "SELECT id FROM orders WHERE status = 'completed' OR id > 5",
        False,
        "required_filters",
    ),
    (
        "filter_only_in_join_on",
        "SELECT o.id FROM orders o "
        "JOIN order_items i ON i.order_id = o.id AND o.status = 'completed'",
        False,
        "required_filters",
    ),
    (
        "filter_forgotten_in_subquery",
        "SELECT id FROM (SELECT id FROM orders) AS q",
        False,
        "required_filters",
    ),
    (
        "filter_exact",
        "SELECT id FROM orders WHERE orders.status = 'completed'",
        True,
        None,
    ),
    ("limit_added", "SELECT id FROM restaurants", True, None),
    ("limit_kept", "SELECT id FROM restaurants LIMIT 100", True, None),
    ("limit_replaced", "SELECT id FROM restaurants LIMIT 999999", True, None),
    (
        "group_by_no_limit",
        "SELECT status, COUNT(*) FROM restaurants GROUP BY status",
        True,
        None,
    ),
    (
        "union_of_selects",
        "SELECT id FROM restaurants UNION SELECT id FROM restaurants",
        True,
        None,
    ),
    ("date_trunc_ok", "SELECT DATE_TRUNC('month', CURRENT_DATE)", True, None),
    ("cast_ok", "SELECT CAST(id AS TEXT) FROM restaurants", True, None),
    (
        "case_ok",
        "SELECT CASE WHEN id > 1 THEN 'big' ELSE 'small' END FROM restaurants",
        True,
        None,
    ),
    ("now_ok", "SELECT now()", True, None),
    ("schema_table_ok", "SELECT id FROM public.restaurants", True, None),
    (
        "double_counting_trap",
        "SELECT SUM(orders.total_amount) FROM orders "
        "JOIN order_items ON order_items.order_id = orders.id "
        "WHERE orders.status = 'completed'",
        False,
        "double_counting",
    ),
    (
        "double_counting_aliases",
        "SELECT SUM(o.total_amount) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE o.status = 'completed'",
        False,
        "double_counting",
    ),
    (
        "double_counting_chain",
        "SELECT SUM(o.total_amount) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "JOIN order_refunds r ON r.item_id = i.id "
        "WHERE o.status = 'completed'",
        False,
        "double_counting",
    ),
    (
        "count_distinct_with_join_ok",
        "SELECT COUNT(DISTINCT o.id) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE o.status = 'completed'",
        True,
        None,
    ),
    (
        "count_star_with_join_ok",
        "SELECT COUNT(*) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE o.status = 'completed'",
        True,
        None,
    ),
    (
        "sum_items_with_join_ok",
        "SELECT SUM(i.qty) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE o.status = 'completed'",
        True,
        None,
    ),
    (
        "subquery_sums_first_ok",
        "SELECT s.total FROM "
        "(SELECT order_id, SUM(qty) AS total FROM order_items GROUP BY order_id) s "
        "JOIN orders o ON o.id = s.order_id "
        "WHERE o.status = 'completed'",
        True,
        None,
    ),
    (
        "avg_over_with_avg",
        "WITH x AS (SELECT AVG(id) AS a FROM restaurants) SELECT AVG(a) FROM x",
        False,
        "average_of_averages",
    ),
    (
        "avg_over_listed",
        "SELECT AVG(avg_revenue) FROM orders WHERE orders.status = 'completed'",
        False,
        "average_of_averages",
    ),
    (
        "avg_plain_ok",
        "SELECT AVG(total) FROM orders WHERE orders.status = 'completed'",
        True,
        None,
    ),
    (
        "sum_div_count_ok",
        "SELECT SUM(total) / COUNT(*) FROM orders WHERE orders.status = 'completed'",
        True,
        None,
    ),
    (
        "ratio_sides_ok",
        "SELECT COALESCE(num.status, den.status) AS status, "
        "CAST(num.value AS NUMERIC) / NULLIF(den.value, 0) AS value "
        "FROM (SELECT status, COUNT(*) AS value FROM orders "
        "WHERE orders.status = 'completed' GROUP BY status) AS num FULL OUTER JOIN "
        "(SELECT status, SUM(qty) AS value FROM order_items GROUP BY status) AS den "
        "ON num.status = den.status",
        True,
        None,
    ),
    (
        "overlap_shape_ok",
        "SELECT status, SUM(m) AS value FROM (SELECT DISTINCT id, status, total AS m "
        "FROM orders WHERE orders.status = 'completed') AS overlap GROUP BY status",
        True,
        None,
    ),
    (
        "outer_sum_over_join_blocked",
        "SELECT SUM(num.value) AS value "
        "FROM (SELECT status, COUNT(*) AS value FROM orders "
        "WHERE orders.status = 'completed' GROUP BY status) AS num JOIN "
        "(SELECT status, COUNT(*) AS value FROM restaurants GROUP BY status) AS den "
        "ON num.status = den.status",
        False,
        "double_counting",
    ),
    (
        "ungrouped_derived_sum_blocked",
        "SELECT SUM(x.total) AS value FROM (SELECT total FROM order_items) AS x",
        False,
        "double_counting",
    ),
    (
        "nongrouped_join_blocked",
        "SELECT COALESCE(num.status, den.status) AS status, "
        "CAST(num.value AS NUMERIC) / NULLIF(den.value, 0) AS value "
        "FROM (SELECT status, COUNT(*) AS value FROM orders "
        "WHERE orders.status = 'completed' GROUP BY status) AS num FULL OUTER JOIN "
        "(SELECT status, SUM(qty) AS value FROM order_items GROUP BY status) AS den "
        "ON num.value = den.value",
        False,
        "double_counting",
    ),
    (
        "derived_non_equality_blocked",
        "SELECT s.total FROM (SELECT order_id, SUM(qty) AS total FROM order_items "
        "GROUP BY order_id) AS s JOIN orders AS o ON o.id = s.order_id AND s.total > 0 "
        "WHERE o.status = 'completed'",
        False,
        "double_counting",
    ),
]


@pytest.mark.parametrize("case_id,sql,ok,rule", CASES, ids=[case[0] for case in CASES])
def test_case(case_id, sql, ok, rule) -> None:
    report = check_sql(sql, CATALOG)
    assert report.ok is ok, report.reasons
    if rule is None:
        assert report.rules == []
        assert report.reasons == []
    else:
        assert rule in report.rules
        assert report.reasons != []


def test_limit_added() -> None:
    assert "LIMIT 50001" in check_sql("SELECT id FROM restaurants", CATALOG).sql


def test_limit_kept() -> None:
    sql = check_sql("SELECT id FROM restaurants LIMIT 100", CATALOG).sql
    assert "LIMIT 100" in sql


def test_limit_replaced() -> None:
    sql = check_sql("SELECT id FROM restaurants LIMIT 999999", CATALOG).sql
    assert "LIMIT 50001" in sql and "999999" not in sql


def test_group_by_left_without_limit() -> None:
    sql = check_sql("SELECT status, COUNT(*) FROM restaurants GROUP BY status", CATALOG).sql
    assert "LIMIT" not in sql.upper()


def test_schema_table_recorded() -> None:
    report = check_sql("SELECT id FROM public.restaurants", CATALOG)
    assert report.tables == ["public.restaurants"]


def test_double_counting_message() -> None:
    report = check_sql(
        "SELECT SUM(o.total_amount) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE o.status = 'completed'",
        CATALOG,
    )
    assert report.rules == ["double_counting"]
    assert report.reasons == [
        "This query adds up `public.orders.total_amount` after joining "
        "`public.order_items`, which has many rows for each `public.orders` row. "
        "Each `public.orders` row would be counted once per `public.order_items` "
        "row. Add up `public.order_items` first in a sub-query, or don't join it."
    ]


def test_average_of_averages_message() -> None:
    report = check_sql(
        "SELECT AVG(avg_revenue) FROM orders WHERE orders.status = 'completed'",
        CATALOG,
    )
    assert report.rules == ["average_of_averages"]
    assert report.reasons == [
        "This query averages numbers that are already averages (`avg_revenue`). "
        "Work out the average as total ÷ count instead."
    ]


def test_no_link_in_catalog_ok() -> None:
    bare = Catalog(
        tables=["public.orders", "public.order_items"],
        required_filters=[
            RequiredFilter(
                table="public.orders",
                sql="orders.status = 'completed'",
                reason="completed orders only",
            )
        ],
    )
    report = check_sql(
        "SELECT SUM(o.total_amount) FROM orders o "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE o.status = 'completed'",
        bare,
    )
    assert report.ok is True


def test_fake_plan_above_limit_blocked() -> None:
    def explain(sql: str) -> dict:
        return [{"Plan": {"Total Cost": 6000000}}]

    report = check_sql("SELECT id FROM restaurants", CATALOG, explain=explain)
    assert report.ok is False
    assert report.rules == ["too_heavy"]
    assert report.reasons == [
        "This query looks too heavy to run safely (Postgres estimates a cost "
        "of `6000000`; the limit is `5000000`). Try a shorter period or fewer details."
    ]


def test_fake_plan_under_limit_ok() -> None:
    def explain(sql: str) -> dict:
        return [{"Plan": {"Total Cost": 100}}]

    report = check_sql("SELECT id FROM restaurants", CATALOG, explain=explain)
    assert report.ok is True


def test_failing_explain_blocks() -> None:
    def explain(sql: str) -> dict:
        raise RuntimeError("boom")

    report = check_sql("SELECT id FROM restaurants", CATALOG, explain=explain)
    assert report.ok is False
    assert report.rules == ["too_heavy"]
    assert report.reasons == ["Charie couldn't estimate this query: `boom`."]


def test_heavy_check_skipped_when_rule_1_fails() -> None:
    def explain(sql: str) -> dict:
        raise AssertionError("the database must never be asked")

    report = check_sql("DELETE FROM restaurants", CATALOG, explain=explain)
    assert report.ok is False
    assert report.rules == ["one_select"]
