"""Quoting for the structure scan's own fixed queries (P07.6).

Every database name in a scan query goes through these helpers; a name
is never pasted into SQL as it is.
"""


def quote_ident(name: str) -> str:
    """One `"quoted"` identifier, with embedded quotes doubled."""
    return '"' + name.replace('"', '""') + '"'


def table_ref(schema: str, table: str) -> str:
    """`"schema"."table"` for a FROM clause."""
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def quote_literal(value: str) -> str:
    """One `'quoted'` string literal, for settings like the time zone."""
    return "'" + value.replace("'", "''") + "'"
