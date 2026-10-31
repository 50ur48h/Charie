"""Recipe model and fragment check (P09.1).

A recipe says how one business number is calculated; code turns it into
SQL so the AI never writes SQL for a known number.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class RecipeError(ValueError):
    """A recipe or query-build refusal, in plain English."""


class ReportedCheck(BaseModel):
    """One number from the documents a recipe answer must match."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    number_text: str
    period_start: str
    period_end: str


class RecipeCheck(BaseModel):
    """One check a recipe passed, failed, or skipped."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["runs", "believable", "matches_documents", "parts_add_up", "self_test"]
    passed: bool | None = None
    text: str = ""


class RecipeDimension(BaseModel):
    """One way to split a recipe number: a column or a time grain."""

    model_config = ConfigDict(extra="forbid")

    key: str
    title: str = ""
    kind: Literal["attribute", "time"]
    table: str = ""
    expression: str = ""
    label_expression: str = ""
    grain: Literal["day", "week", "month", "quarter", "year"] | None = None

    @model_validator(mode="after")
    def _grain_matches_kind(self) -> "RecipeDimension":
        if self.kind == "time" and self.grain is None:
            raise ValueError("Time dimensions need a grain.")
        if self.kind == "attribute" and self.grain is not None:
            raise ValueError("Attribute dimensions take no grain.")
        return self


class Recipe(BaseModel):
    """How one business number is calculated. Ratios divide two recipes."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["simple", "ratio"]
    table: str = ""
    aggregate: Literal["sum", "count", "count_distinct"] | None = None
    expression: str = ""
    filters: list[str] = []
    time_column: str = ""
    time_column_type: Literal["date", "timestamp", "timestamptz"] | None = None
    numerator: str = ""
    denominator: str = ""
    dimensions: list[RecipeDimension] = []
    unit: Literal["money", "count", "percent", "ratio"] = "count"
    currency: str = ""
    steps_in_words: list[str] = []
    reported_checks: list[ReportedCheck] = []
    joins: list[str] = []
    tests: list[RecipeCheck] = []
    sql_preview: str = ""
    tested_at: str = ""

    @model_validator(mode="after")
    def _fields_match_kind(self) -> "Recipe":
        if self.kind == "simple":
            missing = [
                name
                for name in ("table", "aggregate", "expression", "time_column")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(f"Simple recipes need {', '.join(missing)}.")
            if self.time_column_type is None:
                raise ValueError("Simple recipes need a time column type.")
            if self.expression == "*" and self.aggregate != "count":
                raise ValueError("Only count may use `*` as its expression.")
        else:
            if not self.numerator or not self.denominator:
                raise ValueError("Ratio recipes need a numerator and a denominator.")
            set_fields = [
                name for name in ("table", "expression", "time_column") if getattr(self, name)
            ]
            if self.aggregate is not None:
                set_fields.append("aggregate")
            if self.time_column_type is not None:
                set_fields.append("time_column_type")
            if set_fields:
                raise ValueError(f"Ratio recipes take none of {', '.join(set_fields)}.")
        return self

    @model_validator(mode="after")
    def _unit_and_currency(self) -> "Recipe":
        if self.unit == "money":
            if len(self.currency) != 3 or not self.currency.isalpha():
                raise ValueError("Money recipes need a 3-letter currency.")
        elif self.currency:
            raise ValueError("Only money recipes take a currency.")
        return self

    @model_validator(mode="after")
    def _steps_in_words(self) -> "Recipe":
        if not 2 <= len(self.steps_in_words) <= 6:
            raise ValueError("Recipes need 2 to 6 steps in words.")
        return self


class DimensionDetails(BaseModel):
    """A dimension entry: a real column (or time grain) recipes may split by."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["attribute", "time"]
    table: str = ""
    column: str = ""
    label_column: str = ""
    grain: Literal["day", "week", "month", "quarter", "year"] | None = None
    unique_with: list[Any] = []

    @model_validator(mode="after")
    def _grain_matches_kind(self) -> "DimensionDetails":
        if self.kind == "time" and self.grain is None:
            raise ValueError("Time dimensions need a grain.")
        if self.kind == "attribute" and self.grain is not None:
            raise ValueError("Attribute dimensions take no grain.")
        return self


class FragmentInfo(BaseModel):
    """The tables and columns one recipe expression reads."""

    model_config = ConfigDict(extra="forbid")

    tables: list[str]
    columns: list[str]


def check_fragment(text: str) -> FragmentInfo:
    """Check one SQL expression inside a recipe; lists its tables and columns."""
    import sqlglot
    from sqlglot import exp
    from sqlglot.errors import SqlglotError

    from charie.shared.safety.sql_check import is_dangerous_function

    if not text or not text.strip():
        raise RecipeError("A recipe expression can't be empty.")
    if ";" in text:
        raise RecipeError("A recipe expression holds no `;`.")
    try:
        tree = sqlglot.parse_one(text, read="postgres")
    except SqlglotError as err:
        raise RecipeError(f"Charie couldn't read this recipe expression: `{text}`.") from err
    if tree is None:
        raise RecipeError("A recipe expression can't be empty.")
    if tree.find(exp.Select) is not None or tree.find(exp.Subquery) is not None:
        raise RecipeError("A recipe expression holds no subquery.")
    if tree.find(exp.Window) is not None:
        raise RecipeError("Recipe expressions use no window functions.")
    if tree.find(exp.AggFunc) is not None:
        raise RecipeError("Aggregates live in the recipe, not in its expressions.")
    for node in tree.find_all(exp.Func):
        if isinstance(node, (exp.Case, exp.Cast, exp.If)):
            continue
        name = node.sql(dialect="postgres").split("(")[0].strip().upper().split(".")[-1]
        if not name or any(char.isspace() for char in name):
            continue
        if is_dangerous_function(name):
            raise RecipeError(f"`{name}` is a dangerous function and isn't allowed.")
    tables: set[str] = set()
    columns: set[str] = set()
    for column in tree.find_all(exp.Column):
        table = column.table
        if not table:
            raise RecipeError("Every column names its table, like `orders.status`.")
        tables.add(table)
        columns.add(f"{table}.{column.name}")
    return FragmentInfo(tables=sorted(tables), columns=sorted(columns))
