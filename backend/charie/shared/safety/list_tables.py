"""List a database's tables as `schema.table`, one per line."""

import argparse
import sys


def list_tables(connector) -> list[str]:
    """Every `schema.table` in the database, once each."""
    result = connector.run_query(
        "SELECT schemaname, tablename FROM pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
        "ORDER BY 1, 2"
    )
    return [f"{row[0]}.{row[1]}" for row in result.rows]


def main(argv: list[str] | None = None) -> int:
    """Usage: list_tables --database URL."""
    parser = argparse.ArgumentParser(description="List a database's tables.")
    parser.add_argument("--database", required=True, help="Customer database URL.")
    args = parser.parse_args(argv)

    from charie.shared.connectors.postgres import PostgresConnector

    for name in list_tables(PostgresConnector.from_url(args.database)):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
