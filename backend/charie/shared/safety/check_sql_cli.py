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


def load_knowledge(db_url: str):
    """Our draft knowledge, else the published version; the mode line says which."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from charie.shared.knowledge import versions
    from charie.shared.knowledge.catalog import build_catalog

    engine = create_engine(db_url)
    try:
        with Session(engine) as session:
            version = versions.get_draft(session) or versions.get_published(session)
            if version is None:
                return None, MODE_NO_KNOWLEDGE
            catalog = build_catalog(session, version.id)
            return catalog, (
                f"Mode: knowledge version {version.number} ({version.status}): "
                f"{len(catalog.tables)} tables, {len(catalog.links)} links."
            )
    finally:
        engine.dispose()


def load_catalog(path: str) -> Catalog:
    """Read extra rules (forbidden tables, filters, links) from a JSON file."""
    import json

    with open(path, encoding="utf-8") as handle:
        return Catalog.model_validate(json.load(handle))


def has_knowledge(connector) -> bool:
    """Our database holds a knowledge version (`kb_versions` has rows)."""
    result = connector.run_query("SELECT 1 FROM kb_versions LIMIT 1")
    return len(result.rows) > 0


def catalog_for_mode(table_names: list[str], extras: list | None = None) -> Catalog:
    """Every listed table allowed; knowledge and `--catalog-file` rules on top."""
    tables = list(dict.fromkeys(table_names))
    forbidden: list = []
    required: list = []
    links: list = []
    average: list = []
    for extra in extras or []:
        tables = list(dict.fromkeys([*tables, *extra.tables]))
        forbidden.extend(extra.forbidden_tables)
        required.extend(extra.required_filters)
        links.extend(extra.links)
        average.extend(extra.average_columns)
    return Catalog(
        tables=tables,
        forbidden_tables=forbidden,
        required_filters=required,
        links=links,
        average_columns=average,
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
            knowledge, mode = load_knowledge(require_env("DATABASE_URL"))
        else:
            knowledge, mode = None, MODE_NO_KNOWLEDGE
        print(mode)
        extras = [knowledge] if knowledge is not None else []
        if args.catalog_file:
            extras.append(load_catalog(args.catalog_file))
            print(f"Extra rules from {args.catalog_file}.")
        catalog = catalog_for_mode(list_tables(practice), extras)
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
