"""Rule 1-4 cases: one table of (id, sql, ok, rule)."""

import pytest

from charie.shared.safety.catalog import Catalog, RequiredFilter
from charie.shared.safety.sql_check import check_sql

CATALOG = Catalog(
    tables=["public.orders", "public.order_items", "public.restaurants"],
    forbidden_tables=["public.orders_old"],
    required_filters=[
        RequiredFilter(
            table="public.orders",
            sql="orders.status = 'completed'",
            reason="completed orders only",
        )
    ],
)

# (id, sql, ok, rule or None).
CASES = [
    ("plain_aggregate", "SELECT COUNT(*) FROM restaurants", True, None),
    ("with_select", "WITH x AS (SELECT id FROM restaurants) SELECT id FROM x", True, None),
    ("two_statements", "SELECT 1; SELECT 2", False, "one_select"),
    ("delete", "DELETE FROM orders WHERE id = 1", False, "one_select"),
    (
        "delete_in_with",
        "WITH x AS (DELETE FROM orders RETURNING id) SELECT * FROM x",
        False,
        "one_select",
    ),
    ("select_into", "SELECT * INTO t2 FROM restaurants", False, "one_select"),
    ("for_update", "SELECT id FROM restaurants FOR UPDATE", False, "one_select"),
    ("for_share", "SELECT id FROM restaurants FOR SHARE", False, "one_select"),
    ("pg_class", "SELECT * FROM pg_class", False, "allowed_tables"),
    (
        "information_schema",
        "SELECT table_name FROM information_schema.tables",
        False,
        "allowed_tables",
    ),
    ("unknown_table", "SELECT * FROM foo", False, "allowed_tables"),
    ("forbidden_table", "SELECT * FROM orders_old", False, "allowed_tables"),
    ("pg_sleep", "SELECT pg_sleep(5)", False, "functions"),
    ("dblink", "SELECT dblink('x', 'SELECT 1')", False, "functions"),
    ("unknown_function", "SELECT frobnicate(id) FROM restaurants", False, "functions"),
    (
        "generate_series",
        "SELECT * FROM generate_series(1, 10)",
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
        "SELECT * FROM orders WHERE orders.status = 'completed'",
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
    ("lock_table", "LOCK TABLE restaurants", False, "one_select"),
    ("schema_table_ok", "SELECT * FROM public.restaurants", True, None),
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
    report = check_sql("SELECT * FROM public.restaurants", CATALOG)
    assert report.tables == ["public.restaurants"]
