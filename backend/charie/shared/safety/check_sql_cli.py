"""Check one query from the shell, on the practice database only (P05.13).

Run as `uv run python -m charie.shared.safety.check_sql_cli "<SQL>"`.
"""

import argparse
import sys

from charie.shared.safety.catalog import Catalog
from charie.shared.safety.sql_check import check_sql

MODE_NO_KNOWLEDGE = (
    "Mode: no knowledge yet. Every table in the database is allowed; "
    "there are no owner rules or table links to check yet."
)
MODE_KNOWLEDGE_UNREADABLE = (
    "Mode: no knowledge yet. Knowledge exists, but this checker can't read "
    "it yet, so every table is allowed and no owner rules or links are checked."
)


def load_catalog(path: str) -> Catalog:
    """Read extra rules (forbidden tables, filters, links) from a JSON file."""
    import json

    with open(path, encoding="utf-8") as handle:
        return Catalog.model_validate(json.load(handle))


def has_knowledge(connector) -> bool:
    """Our database holds a knowledge version (`kb_versions` has rows)."""
    result = connector.run_query("SELECT 1 FROM kb_versions LIMIT 1")
    return len(result.rows) > 0


def catalog_for_mode(table_names: list[str], extra: Catalog | None = None) -> Catalog:
    """Every listed table allowed; anything from `--catalog-file` on top."""
    tables = list(dict.fromkeys(table_names))
    if extra is None:
        return Catalog(tables=tables)
    merged = list(dict.fromkeys([*tables, *extra.tables]))
    return Catalog(
        tables=merged,
        forbidden_tables=list(extra.forbidden_tables),
        required_filters=list(extra.required_filters),
        links=list(extra.links),
        average_columns=list(extra.average_columns),
    )


def run(argv: list[str] | None = None, *, ours=None, practice=None) -> int:
    """Check the query and explain the verdict; 0 allowed, 1 blocked, 2 error."""
    from charie.shared.config import require_env
    from charie.shared.connectors.postgres import PostgresConnector

    parser = argparse.ArgumentParser(description="Rule one SQL query before it runs.")
    parser.add_argument("sql", nargs="?", help="The SQL to check.")
    parser.add_argument("--file", help="Read the SQL from this file instead.")
    parser.add_argument("--count", action="store_true", help="Count the rows it returns.")
    parser.add_argument("--catalog-file", help="Extra rules as a JSON Catalog.")
    args = parser.parse_args(argv)

    try:
        if args.file:
            with open(args.file, encoding="utf-8") as handle:
                sql = handle.read()
        elif args.sql:
            sql = args.sql
        else:
            print("Give a query to check, or --file <path>.")
            return 2
        if ours is None:
            ours = PostgresConnector.from_url(require_env("DATABASE_URL"))
        if practice is None:
            practice = PostgresConnector.from_url(require_env("PRACTICE_DB_URL"))
        from charie.shared.safety.list_tables import list_tables

        if has_knowledge(ours):
            print(MODE_KNOWLEDGE_UNREADABLE)
        else:
            print(MODE_NO_KNOWLEDGE)
        extra = load_catalog(args.catalog_file) if args.catalog_file else None
        if extra is not None:
            print(f"Extra rules from {args.catalog_file}.")
        catalog = catalog_for_mode(list_tables(practice), extra)
        report = check_sql(sql, catalog, explain=practice.explain)
        if not report.ok:
            print("Blocked:")
            for position, reason in enumerate(report.reasons, start=1):
                print(f"{position}. {reason}")
            print("The query that would run:")
            print(report.sql)
            return 1
        print("Allowed.")
        print("The query that would run:")
        print(report.sql)
        if args.count:
            count_sql = f"SELECT COUNT(*) FROM ({report.sql}) AS q"
            counted = practice.run_checked(count_sql, catalog)
            print(f"It returns {counted.rows[0][0]} rows on the practice database.")
        return 0
    except Exception as err:  # noqa: BLE001
        print(f"Error: {err}")
        return 2


def main(argv: list[str] | None = None) -> int:
    """Usage: check_sql_cli "<SQL>" [--file PATH] [--count] [--catalog-file PATH]."""
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
