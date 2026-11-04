"""``run_sql`` — the only tool that touches customer data (architecture 4.6, 7.1)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from charie.agent.tools.base import MAX_RENDERED_CHARS, Tool, ToolContext, ToolError
from charie.catalog.browse import NoCatalogError
from charie.connectors.base import ConnectorError
from charie.dal import run as dal_run
from charie.dal.artifacts import encodable
from charie.dal.errors import PolicyViolation
from charie.dal.masking import MaskedFrame
from charie.dal.service import Execution
from charie.datasources.service import NotFoundError

#: `preview_rows` is public because it is the rule, not an implementation detail.
__all__ = ["PREVIEW_CHARS", "PREVIEW_ROWS_MIN", "RUN_SQL", "preview_rows"]

#: What a preview may cost the prompt, measured on the payload that is actually rendered (B-113).
PREVIEW_CHARS = MAX_RENDERED_CHARS - 100

#: The fewest rows worth showing, whatever they cost.
PREVIEW_ROWS_MIN = 3


class RunSqlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sql: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "One SELECT statement, using only tables and columns from the catalog. "
            "No semicolons beyond the single statement, no DDL, no system schemas."
        ),
    )
    purpose: str = Field(
        min_length=1,
        max_length=300,
        description="One line on what this query is for. It appears in the run's trace.",
    )


class RunSqlOut(BaseModel):
    """What came back, and the id a citation will name."""

    execution_id: str
    columns: list[str]
    rows: list[list[object]] = Field(
        description="Masked and capped. A preview, not the whole result."
    )
    row_count: int
    truncated: bool = False
    masked_columns: list[str] = Field(
        default_factory=list[str],
        description="Columns whose values were obscured by policy before you saw them.",
    )
    duration_ms: int | None = None
    tables: list[str] = Field(
        default_factory=list[str],
        description=(
            "The tables this statement read, as the validator resolved them "
            "against the catalog — not as the model spelled them (B-093)."
        ),
    )


async def _run_sql(context: ToolContext, params: BaseModel) -> BaseModel:
    args = params if isinstance(params, RunSqlIn) else RunSqlIn.model_validate(params)
    if context.data_source_id is None:
        raise ToolError(
            "No data source is selected for this run, so there is nothing to query.",
            code="no_data_source",
        )

    # B-176. The run's own connection where it has one.
    lease = context.lease

    try:
        borrowed = (
            await lease.connector()
            if lease is not None and lease.matches(context.org_id, context.data_source_id)
            else None
        )
        execution = await dal_run(
            org_id=context.org_id,
            data_source_id=context.data_source_id,
            sql=args.sql,
            actor_user_id=context.actor_user_id,
            run_id=context.run_id,
            connector=borrowed,
        )
    except PolicyViolation as violation:
        # The refusal the whole design is for.
        raise ToolError(str(violation), code=str(violation.code), repairable=True) from violation
    except (NotFoundError, NoCatalogError) as error:
        raise ToolError(str(error), code="no_catalog") from error
    except ConnectorError as error:
        # Already sanitized by the connector: names what failed, never an address or a credential.
        if lease is not None and not error.statement_fault:
            await lease.forget()
        raise ToolError(
            str(error), code="engine_error", repairable=error.statement_fault
        ) from error

    frame = execution.frame

    def rendered(candidate: list[list[object]]) -> str:
        """The payload those rows would produce, exactly as the model sees it."""
        return _out(execution, frame, candidate).model_dump_json(indent=2)

    shown = preview_rows(frame.rows, rendered)
    return _out(execution, frame, shown)


def _out(execution: Execution, frame: MaskedFrame, rows: list[list[object]]) -> RunSqlOut:
    """One payload, built once, so the measurement and the result cannot differ."""
    return RunSqlOut(
        execution_id=str(execution.execution_id) if execution.execution_id else "",
        columns=list(frame.columns),
        rows=rows,
        row_count=execution.row_count,
        # True when the DAL capped the result or when the budget did.
        truncated=execution.truncated or len(rows) < len(frame.rows),
        masked_columns=list(frame.masked_columns),
        duration_ms=execution.duration_ms,
        # From the validator rather than from the SQL text.
        tables=[str(table) for table in execution.validated.tables],
    )


def preview_rows(
    rows: Sequence[Sequence[object]],
    render: Callable[[list[list[object]]], str],
) -> list[list[object]]:
    """As many rows as the budget pays for, measured on what will be sent."""
    encoded = [[encodable(value) for value in row] for row in rows]
    if not encoded or len(render(encoded)) <= PREVIEW_CHARS:
        return encoded

    # Proportional first guess, then step down.
    over = len(render(encoded))
    keep = max(PREVIEW_ROWS_MIN, len(encoded) * PREVIEW_CHARS // over)
    while keep > PREVIEW_ROWS_MIN and len(render(encoded[:keep])) > PREVIEW_CHARS:
        keep = max(PREVIEW_ROWS_MIN, keep * 4 // 5)
    return encoded[:keep]


RUN_SQL = Tool(
    name="run_sql",
    description=(
        "Run one read-only SELECT against the selected data source and get back "
        "the rows. Every statement is checked against the catalog and the column "
        "policy first; anything ungrounded is refused with a reason."
    ),
    params=RunSqlIn,
    handler=_run_sql,
    budget_cost=1,
)
