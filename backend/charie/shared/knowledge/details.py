"""Checked `details` shapes for knowledge entries (P07.3).

One Pydantic model per entry kind, from architecture 05 section 3.
Fixed models forbid unknown fields; the later kinds (metric onward)
accept extra fields because Phases 8-9 add their own.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """A details model: unknown fields are refused."""

    model_config = ConfigDict(extra="forbid")


class Source(BaseModel):
    """Where one entry came from: a query, a profile, notes, or you."""

    model_config = ConfigDict(extra="forbid")

    type: str
    text: str | None = None
    quote: str | None = None
    sql: str | None = None
    at: str | None = None


class ForeignKeyRef(StrictModel):
    columns: list[str] = []
    ref_table: str = ""
    ref_columns: list[str] = []


class TableDetails(StrictModel):
    schema: str
    name: str
    is_view: bool = False
    row_estimate: int | None = None
    comment: str = ""
    primary_key: list[str] = []
    foreign_keys: list[ForeignKeyRef] = []
    columns: list[str] = []
    profiled_at: str | None = None
    sampled: bool = False
    rows_profiled: int | None = None
    grain: str = ""
    explained: bool = False
    checks_failed: list[str] = []


class TopValue(StrictModel):
    value: Any = None
    count: int = 0


class ColumnProfile(StrictModel):
    rows_seen: int | None = None
    sampled: int | None = None
    empty: int | None = None
    empty_share: float | None = None
    distinct: int | None = None
    top_values: list[TopValue] = []
    min: Any = None
    max: Any = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    pattern_share: float | None = None
    date_from: str | None = None
    date_to: str | None = None
    strict: bool = False


class ColumnDetails(StrictModel):
    schema: str
    table: str
    name: str
    position: int | None = None
    data_type: str = ""
    nullable: bool | None = None
    is_primary_key: bool = False
    is_unique: bool = False
    comment: str = ""
    profile: ColumnProfile | None = None
    unit: str = ""
    unit_name: str = ""
    currency: str = ""
    refers_to: str = ""
    explained: bool = False
    checks_failed: list[str] = []


class LinkDetails(StrictModel):
    from_table: str
    from_columns: list[str]
    to_table: str
    to_columns: list[str]
    found_by: Literal["foreign_key", "matching_name"] = "foreign_key"
    cardinality: Literal["many_to_one", "one_to_one"] = "many_to_one"
    match_share: float | None = None
    orphans: int | None = None
    empty_from: int | None = None
    sampled: bool = False
    tested_at: str | None = None


class DataRangeColumn(StrictModel):
    column: str = ""
    date_from: str | None = None
    date_to: str | None = None
    non_empty: bool = False


class DataRangeDetails(StrictModel):
    table: str
    date_column: str
    date_from: str
    date_to: str
    exact: bool = False
    columns: list[DataRangeColumn] = []


class RuleDetails(StrictModel):
    rule_type: Literal[
        "never_use_table", "always_filter", "exclude_values", "currency", "required_note"
    ]
    table: str = ""
    column: str = ""
    values: list[str] = []
    currency: str = ""
    note_text: str = ""
    applies_to_tables: list[str] = []
    applies_to_words: list[str] = []


class StyleDetails(StrictModel):
    topics: list[str] = []


class NameItem(StrictModel):
    id: Any = None
    name: str = ""


class NameDetails(StrictModel):
    table: str
    id_column: str
    name_column: str
    items: list[NameItem] = []
    truncated: bool = False


class LaterDetails(BaseModel):
    """Metric and later kinds: `tables` and `columns`, plus whatever
    Phases 8-9 add (recipes arrive in P09.1)."""

    model_config = ConfigDict(extra="allow")

    tables: list[str] = []
    columns: list[str] = []


class MetricDetails(LaterDetails):
    pass


class DimensionDetails(LaterDetails):
    pass


class CodeDetails(LaterDetails):
    pass


class EventDetails(LaterDetails):
    pass


class DataProblemDetails(LaterDetails):
    pass


class DefaultDetails(LaterDetails):
    pass


class CalendarDetails(LaterDetails):
    pass


class HowToDetails(LaterDetails):
    pass


class ExampleDetails(LaterDetails):
    pass


DETAILS_MODELS: dict[str, type[BaseModel]] = {
    "table": TableDetails,
    "column": ColumnDetails,
    "link": LinkDetails,
    "data_range": DataRangeDetails,
    "rule": RuleDetails,
    "style": StyleDetails,
    "name": NameDetails,
    "metric": MetricDetails,
    "dimension": DimensionDetails,
    "code": CodeDetails,
    "event": EventDetails,
    "data_problem": DataProblemDetails,
    "default": DefaultDetails,
    "calendar": CalendarDetails,
    "how_to": HowToDetails,
    "example": ExampleDetails,
}


def check_details(kind: str, data: dict[str, Any] | None) -> dict[str, Any]:
    """Check `data` against the kind's model; returns the plain mapping."""
    try:
        model = DETAILS_MODELS[kind]
    except KeyError:
        raise ValueError(f"Unknown knowledge kind: {kind!r}.") from None
    if not isinstance(data, dict):
        raise ValueError(f"Details for {kind!r} must be a mapping.")
    return model.model_validate(data).model_dump()
