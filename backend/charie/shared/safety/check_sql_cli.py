"""One-shot safety check from the shell (and the pattern the data tool uses)."""

import argparse
import json
import sys

from charie.shared.safety.catalog import Catalog
from charie.shared.safety.sql_check import HEAVY_QUERY, CheckReport, check_sql, explain_plan


def load_catalog(path: str) -> Catalog:
    """Read the guarded tables from a JSON file."""
    with open(path, encoding="utf-8") as handle:
        return Catalog.model_validate(json.load(handle))


def run_check(
    sql: str, catalog: Catalog, connector=None, explain: bool = False, max_rows: int = 50_000
) -> CheckReport:
    """Check one query; with a connector, also ask the database's own plan."""
    report = check_sql(sql, catalog, max_rows=max_rows)
    if report.ok and explain and connector is not None:
        warning = explain_plan(report.sql, catalog, connector, max_rows=max_rows)
        if warning is not None:
            report.reasons.append(warning)
            report.rules.append(HEAVY_QUERY)
    return report


def print_report(report: CheckReport, estimate: str | None = None) -> None:
    """The verdict in plain words: what passed, what failed, what would run."""
    if report.ok:
        print("Allowed")
    else:
        print("Blocked:")
        for reason in report.reasons:
            print(f"- {reason}")
    print("The query that would run:")
    print(report.sql)
    if estimate is not None:
        print(f"Database row estimate: {estimate}")


def main(argv: list[str] | None = None) -> int:
    """Usage: check_sql_cli --database URL --catalog FILE --query SQL [--explain]."""
    parser = argparse.ArgumentParser(description="Rule one SQL query before it runs.")
    parser.add_argument("--database", required=True, help="Customer database URL.")
    parser.add_argument("--catalog", required=True, help="Guarded tables JSON file.")
    parser.add_argument("--query", required=True, help="The SQL to check.")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=50_000,
        help="Row cap for the LIMIT rewrite and the plan check.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Also ask the database's own plan for a row estimate.",
    )
    parser.add_argument(
        "--list-tables",
        action="store_true",
        help="Print the database's schema.table names instead of checking.",
    )
    args = parser.parse_args(argv)

    from charie.shared.connectors.postgres import PostgresConnector

    connector = PostgresConnector.from_url(args.database)
    if args.list_tables:
        from charie.shared.safety.list_tables import list_tables

        for name in sorted(list_tables(connector)):
            print(name)
        return 0
    catalog = load_catalog(args.catalog)
    estimate = _estimate(connector, args.query, catalog, args.max_rows) if args.explain else None
    report = run_check(args.query, catalog, connector, explain=args.explain, max_rows=args.max_rows)
    print_report(report, estimate)
    return 0


def _estimate(connector, sql: str, catalog: Catalog, max_rows: int) -> str | None:
    """The planner's own row count, or None when the query never runs."""
    from charie.shared.safety.sql_check import check_sql as check
    from charie.shared.safety.sql_check import plan_rows

    report = check(sql, catalog, max_rows=max_rows)
    if not report.ok:
        return None
    rows = plan_rows(connector, report.sql)
    return f"{rows} rows" if rows is not None else "unknown"


if __name__ == "__main__":
    sys.exit(main())
