"""Key builders for knowledge entries (P07.3).

Names inside keys are kept exactly as the database spells them: only
titles are slugged, never real table or column names.
"""

import re

_SLUG_RUN = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """Lowercase slug: runs of other characters become `_`, trimmed, 60 max."""
    slug = _SLUG_RUN.sub("_", text.lower()).strip("_")[:60].strip("_")
    return slug or "item"


def table_key(schema: str, table: str) -> str:
    """`table.public.orders`."""
    return f"table.{schema}.{table}"


def column_key(schema: str, table: str, column: str) -> str:
    """`column.public.orders.total_amount`."""
    return f"column.{schema}.{table}.{column}"


def link_key(
    from_schema: str,
    from_table: str,
    from_columns: list[str],
    to_schema: str,
    to_table: str,
    to_columns: list[str],
) -> str:
    """`link.public.orders.restaurant_id~public.restaurants.id`."""
    left = f"{from_schema}.{from_table}." + "+".join(from_columns)
    right = f"{to_schema}.{to_table}." + "+".join(to_columns)
    return f"link.{left}~{right}"


def data_range_key(schema: str, table: str) -> str:
    """`data_range.public.orders`."""
    return f"data_range.{schema}.{table}"


def name_key(schema: str, table: str) -> str:
    """`name.public.restaurants`."""
    return f"name.{schema}.{table}"


def rule_key(rule_type: str, title: str) -> str:
    """`rule.currency.money_is_in_us_dollars`."""
    return f"rule.{rule_type}.{slug(title)}"


def style_key(title: str) -> str:
    """`style.always_add_unaudited_figures`."""
    return f"style.{slug(title)}"


def note_key(kind: str, title: str) -> str:
    """`how_to.notes.investigate_a_drop`."""
    return f"{kind}.notes.{slug(title)}"
