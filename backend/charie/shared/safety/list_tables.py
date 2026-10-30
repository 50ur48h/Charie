"""List a database's tables and views as `schema.table`, one per line."""


def list_tables(connector) -> list[str]:
    """Every `schema.table` in the database, once each.

    Base tables and views outside `pg_catalog` and `information_schema`.
    """
    result = connector.run_query(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
        "AND table_type IN ('BASE TABLE', 'VIEW') "
        "ORDER BY 1, 2"
    )
    return [f"{row[0]}.{row[1]}" for row in result.rows]
