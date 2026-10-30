"""The tables Charie may read, and the rules that guard them (06)."""

from pydantic import BaseModel, field_validator


def normalize_table(name: str) -> str:
    """`schema.table`, lowercase; no schema means `public`."""
    parts = [piece.strip() for piece in name.split(".") if piece.strip()]
    if len(parts) >= 2:
        schema, table = parts[-2], parts[-1]
    elif parts:
        schema, table = "public", parts[0]
    else:
        schema, table = "public", ""
    return f"{schema.lower()}.{table.lower()}"


def normalize_column(name: str) -> str:
    """Column names fold to lowercase, like Postgres."""
    return name.strip().lower()


class RequiredFilter(BaseModel):
    """One condition a table's queries must carry in their WHERE."""

    table: str
    sql: str
    reason: str

    _norm_table = field_validator("table", mode="before")(normalize_table)


class Link(BaseModel):
    """A tested one-to-many join: one row on the left, many on the right."""

    one_table: str
    one_column: str
    many_table: str
    many_column: str

    _norm_tables = field_validator("one_table", "many_table", mode="before")(normalize_table)
    _norm_columns = field_validator("one_column", "many_column", mode="before")(normalize_column)


class Catalog(BaseModel):
    """What the checker may assume: known tables, hard rules, links."""

    tables: list[str] = []
    forbidden_tables: list[str] = []
    required_filters: list[RequiredFilter] = []
    links: list[Link] = []
    average_columns: list[str] = []

    _norm_tables = field_validator("tables", "forbidden_tables", mode="before")(
        lambda names: [normalize_table(name) for name in (names or [])]
    )
    _norm_columns = field_validator("average_columns", mode="before")(
        lambda names: [normalize_column(name) for name in (names or [])]
    )
