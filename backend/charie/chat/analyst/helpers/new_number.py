"""New kinds of numbers: the AI writes each query two ways (P10.7).

When no recipe covers a number, way A writes the direct query and way B
writes it a different way. Code checks both, runs both read-only, and
compares them with the self-test rule. If they agree, the numbers go
into the notebook (marked "not a standard measure yet") and the learner
gets a to-do; if they disagree, no number is used.
"""

import time
from decimal import Decimal

from sqlalchemy import select

from charie.chat.analyst.dates import ResolvedPeriod
from charie.chat.analyst.helpers import data as data_module
from charie.chat.analyst.helpers.tasks import Task, _lock, task_signature
from charie.chat.analyst.notebook import (
    FindingValue,
    Notebook,
    NumberValue,
    TableColumn,
    TableValue,
)
from charie.shared.ai.errors import AiError
from charie.shared.calc.core import (
    CalcError,
    ResultTable,
    difference,
    percent_change,
)
from charie.shared.connectors.base import ConnectorError, QueryBlocked
from charie.shared.db import session_scope
from charie.shared.knowledge.query_builder import QueryBuildError
from charie.shared.knowledge.sql_writer import (
    ExaminerBlocked,
    ExamTask,
    WrittenSql,
    examiner_brief,
    results_agree,
    write_checked_sql,
)
from charie.shared.knowledge.todos import add_learner_todo
from charie.shared.tables.questions import LearnerTodo
from charie.shared.text.numbers import format_count, format_percent

#: New numbers have no recipe unit; counts cover the "how many" questions.
NEW_UNIT = "count"


def brief_input(
    question: str,
    scope_table: str,
    time_column: str,
    time_zone: str,
    splits: list[str],
    period_start: str,
    period_end: str,
    structure: str,
) -> dict:
    """The `write_sql` inputs for one new number; pure so tests pin the ways."""
    return {
        "question": question,
        "period_start": period_start,
        "period_end": period_end,
        "splits": list(splits),
        "scope_table": scope_table,
        "time_column": time_column,
        "time_zone": time_zone,
        "structure": structure,
        "way_guidance": "",
    }


def _filter_words(task: Task, loaded: data_module._Loaded) -> str:
    """The task's filters as words, for the brief's question."""
    parts = []
    for filt in task.filters:
        title = loaded.titles.get(filt.dimension_key, filt.dimension_key)
        values = ", ".join(str(value) for value in filt.values)
        parts.append(f"only {title} {values}")
    return "; ".join(parts)


def new_number_brief(
    session, version_id: int, loaded: data_module._Loaded, task: Task, period: ResolvedPeriod
) -> dict:
    """What both ways may see: the task in words, the real dates, everything.

    The brief is built from the task alone, never from a query, so way B
    can never see way A's SQL. The scope is every learned table: a new
    number has no recipe naming its table.
    """
    words = task.new_metric
    filters = _filter_words(task, loaded)
    if filters:
        words += f" Filters: {filters}."
    tables = ", ".join(sorted(loaded.build_context.tables)) or "the whole database"
    fake = ExamTask(
        question=words,
        metric_key="",
        period_start=period.start.isoformat(),
        period_end=period.end.isoformat(),
        splits=tuple(task.split_by),
        unit=NEW_UNIT,
    )
    brief = examiner_brief(session, version_id, fake, loaded.build_context.time_zone)
    brief["input"]["scope_table"] = tables
    return brief


def _proof(
    task: Task, run_ids: list[int], metric: str, split: dict, period, compare, measure: str
) -> dict:
    """Where a new number came from: both queries, never a recipe."""
    return {
        "task": task_signature(task),
        "recipe_key": "",
        "query_run_ids": run_ids,
        "way": "A+B",
        "checks": [],
        "fact_key": {
            "metric": metric,
            "filters": [
                [filt.dimension_key, sorted(str(value) for value in filt.values)]
                for filt in task.filters
            ],
            "split": split,
            "period": f"{period.start.isoformat()}/{period.end.isoformat()}",
            "compare_period": (
                f"{compare.start.isoformat()}/{compare.end.isoformat()}"
                if compare is not None
                else ""
            ),
            "measure": measure,
        },
    }


def _format_total(total) -> str:
    """A new total in the owner's format; counts have no decimals."""
    if isinstance(total, Decimal) and total == int(total):
        return format_count(str(int(total)))
    return format_count(str(total))


def run_new_number_task(task: Task, ctx, round_no: int = 1) -> None:
    """One new-number task, under the question's lock, in one session."""
    with _lock(ctx.message_id):
        _run_new_number_task(task, ctx, round_no)


def _run_new_number_task(task: Task, ctx, round_no: int = 1) -> None:
    with session_scope() as session:
        book = Notebook(session, ctx.message_id, ctx.chat_id, round=round_no)
        loaded = data_module._Loaded(session, ctx.kb_version_id)
        try:
            periods = data_module._task_periods(task, ctx)
            if not periods:
                raise QueryBuildError("There's no period to work out for.")
            description = (task.new_metric or "a new number").rstrip("?. ")
            metric = f"new:{description.lower()}"
            seq = ctx.log.start("query", f"Working out {description} two ways", task.why)
            per_period = [
                _run_period(session, ctx, task, loaded, book, period) for period in periods
            ]
        except ExaminerBlocked:
            _blocked(ctx, book, task, seq, description)
            return
        except (QueryBlocked, QueryBuildError, ConnectorError, CalcError, AiError) as err:
            _failed(ctx, book, task, seq, description, err)
            return
        if any(not agreed for _, _, agreed, _ in per_period):
            _disagree(ctx, book, task, seq, description, metric, periods, per_period)
            return
        if task.split_by:
            _save_new_split(ctx, book, task, loaded, periods, per_period, seq, description, metric)
        else:
            _save_new_totals(ctx, book, task, loaded, periods, per_period, seq, description, metric)
        _maybe_add_todo(session, task, ctx, description, per_period[0])
        ctx.log.finish(
            seq,
            status="done",
            title=f"Worked out {description} two ways: both agree",
            body=_agree_body(per_period[0]),
            details={
                "sql_a": per_period[0][0].sql,
                "sql_b": per_period[0][1].sql,
                "periods": len(periods),
            },
        )


def _run_period(session, ctx, task, loaded, book, period):
    """One period's A and B: write both, check and run both, compare."""
    brief = new_number_brief(session, ctx.kb_version_id, loaded, task, period)
    connector = data_module.customer_connector(session)
    durations: list[int] = []
    tables: list[str] = []

    def run(sql: str):
        started = time.monotonic()
        try:
            result = connector.run_checked(sql, loaded.catalog)
        finally:
            durations.append(int((time.monotonic() - started) * 1000))
        for table in result.tables:
            if table not in tables:
                tables.append(table)
        return result

    written_a = write_checked_sql(brief, run, way="A", message_id=ctx.message_id)
    written_b = write_checked_sql(brief, run, way="B", message_id=ctx.message_id)
    run_a = data_module._save_run(
        session,
        ctx.message_id,
        task,
        written_a.sql,
        True,
        "ok",
        len(written_a.rows),
        durations[0] if durations else 0,
        None,
        way="A",
        tables=tables,
    )
    run_b = data_module._save_run(
        session,
        ctx.message_id,
        task,
        written_b.sql,
        True,
        "ok",
        len(written_b.rows),
        durations[1] if len(durations) > 1 else 0,
        None,
        way="B",
        tables=tables,
    )
    _validate(written_a)
    _validate(written_b)
    agreed = results_agree(written_a.rows, written_b.rows)
    return written_a, written_b, agreed, (run_a, run_b)


def _validate(written: WrittenSql) -> None:
    """Ragged rows fail like a bad recipe result; the failure shows why."""
    ResultTable(list(written.columns), [list(row) for row in written.rows])


def _agree_body(first) -> str:
    """`Way A: {notes A} Way B: {notes B}`; a notes text with digits is left out."""
    written_a, written_b, _, _ = first
    parts = []
    for way, written in (("A", written_a), ("B", written_b)):
        notes = (written.notes or "").strip()
        if notes and not any(char.isdigit() for char in notes):
            parts.append(f"Way {way}: {notes}")
        else:
            parts.append(f"Way {way}:")
    return " ".join(parts)


def _blocked(ctx, book, task, seq, description) -> None:
    """A blocked way: the failed line, then the finding. No numbers."""
    body = f"Couldn't check {description}: the queries weren't safe to run."
    ctx.log.finish(seq, status="failed", body=body)
    book.add_finding(
        description,
        FindingValue(type="couldnt_check", text=body, task=task_signature(task)),
    )


def _failed(ctx, book, task, seq, description, err) -> None:
    """Any other failure: the failed line, then the finding. No numbers."""
    body = f"Couldn't work out {description} two ways: {err}."
    ctx.log.finish(seq, status="failed", body=body)
    book.add_finding(description, FindingValue(type="failed", text=body, task=task_signature(task)))


def _table(written: WrittenSql) -> ResultTable:
    """One way's rows as a table, for totals."""
    return ResultTable(list(written.columns), [list(row) for row in written.rows])


def _totals(per_period) -> list:
    """Each period's total, or None when a way returned no rows."""
    totals = []
    for written_a, _, _, _ in per_period:
        columns = list(written_a.columns)
        name = columns[-1] if columns else "value"
        total = _table(written_a).total(name) if columns else None
        totals.append(total)
    return totals


def _disagree(ctx, book, task, seq, description, metric, periods, per_period) -> None:
    """The ways differ: no numbers, a finding and a decision line."""
    written_a, written_b, _, _ = per_period[0]
    rows_a = [list(row) for row in written_a.rows]
    rows_b = [list(row) for row in written_b.rows]
    width = max((len(row) for row in rows_a + rows_b), default=1) - 1
    if task.split_by:
        keys_a = {data_module._group_key(row, width) for row in rows_a}
        keys_b = {data_module._group_key(row, width) for row in rows_b}
        union = keys_a | keys_b
        differ = sum(
            1
            for key in union
            if not results_agree(
                [row for row in rows_a if data_module._group_key(row, width) == key],
                [row for row in rows_b if data_module._group_key(row, width) == key],
            )
        )
        text = (
            f"Way A and way B disagree for {description}: "
            f"they differ on {differ} of {len(union)} rows."
        )
    else:
        totals_a = [_table(pair[0]).total(pair[0].columns[-1]) for pair in per_period]
        totals_b = [_table(pair[1]).total(pair[1].columns[-1]) for pair in per_period]
        shown_a = _format_total(totals_a[0]) if totals_a[0] is not None else "nothing"
        shown_b = _format_total(totals_b[0]) if totals_b[0] is not None else "nothing"
        text = f"Way A and way B disagree for {description}: A gave {shown_a}, B gave {shown_b}."
    book.add_finding(
        description,
        FindingValue(type="disagreement", text=text, task=task_signature(task)),
    )
    ctx.log.finish(seq, status="done", title=f"Worked out {description} two ways")
    ctx.log.add(
        "decision",
        f"The two ways disagree for {description}",
        f"{text} I'll look into the difference next round.",
        details={"sql_a": written_a.sql, "sql_b": written_b.sql},
    )


def _save_new_totals(
    ctx, book, task, loaded, periods, per_period, seq, description, metric
) -> None:
    """One number per period, then changes; every description ends the same way."""
    title = f"{description} (not a standard measure yet)"
    totals = _totals(per_period)
    run_ids = [run_id for _, _, _, (run_a, run_b) in per_period for run_id in (run_a, run_b)]
    for period, total in zip(periods, totals, strict=True):
        if total is None:
            book.add_finding(
                title,
                FindingValue(
                    type="nothing_found",
                    text=f"There is no {description} for {period.text}.",
                    task=task_signature(task),
                ),
            )
            continue
        book.add_number(
            f"{title}, {period.text}",
            NumberValue(value=str(total), unit=NEW_UNIT, currency=""),
            proof=_proof(task, run_ids, metric, {}, period, None, "value"),
        )
    if len(periods) == 2 and totals[0] is not None and totals[1] is not None:
        _save_new_change(ctx, book, task, periods, run_ids, title, metric, totals[0], totals[1])


def _save_new_change(ctx, book, task, periods, run_ids, title, metric, new, old) -> None:
    """One comparison's change and % change, or silence when they fail."""
    try:
        change = difference(new, old)
        percent = percent_change(new, old) if change is not None else None
    except CalcError:
        return
    if change is None:
        return
    main, compare = periods[0], periods[1]
    desc = f"Change in {title}, {main.text} vs {compare.text}"
    book.add_number(
        desc,
        NumberValue(value=str(change), unit=NEW_UNIT, currency="", style="change"),
        proof=_proof(task, run_ids, metric, {}, main, compare, "change"),
    )
    if percent is not None:
        book.add_number(
            desc,
            NumberValue(value=str(percent), unit="percent", currency="", style="change"),
            proof=_proof(task, run_ids, metric, {}, main, compare, "percent_change"),
        )
    if percent is None:
        ctx.log.add("found", f"Found: {title} was {_format_total(new)}.")
        return
    direction = "up" if change >= 0 else "down"
    ctx.log.add(
        "found",
        f"Found: {title} was {_format_total(new)}, "
        f"{direction} {format_percent(str(abs(percent)))} on {compare.text}.",
    )


def _save_new_split(ctx, book, task, loaded, periods, per_period, seq, description, metric) -> None:
    """One table per main period, with changes on a comparison."""
    title = f"{description} (not a standard measure yet)"
    main_written = per_period[0][0]
    columns = list(main_written.columns)
    width = len(columns) - 1
    table_columns = []
    for pos, name in enumerate(columns[:-1]):
        key = task.split_by[pos] if pos < len(task.split_by) else name
        table_columns.append(
            TableColumn(key=name, label=loaded.titles.get(key, name), unit="", currency="")
        )
    table_columns.append(
        TableColumn(key=columns[-1], label=task.new_metric, unit=NEW_UNIT, currency="")
    )
    if len(periods) > 1:
        table_columns.append(TableColumn(key="change", label="Change", unit=NEW_UNIT))
        table_columns.append(TableColumn(key="percent_change", label="Change %", unit="percent"))
    for pos, period in enumerate(periods):
        written_a = per_period[pos][0]
        rows = [[data_module._cell(value) for value in row] for row in written_a.rows]
        ordered = data_module._ordered_rows(rows, width, None)
        if len(periods) > 1 and pos == 0:
            compare_rows = {
                data_module._group_key(row, width): row[width] for row in per_period[1][0].rows
            }
            ordered = [
                [*cells, data_module._cell(change), data_module._cell(percent)]
                for cells, (change, percent) in [
                    (cells, _new_row_change(cells, compare_rows, width)) for cells in ordered
                ]
            ]
        elif len(periods) > 1:
            ordered = [[*cells, None, None] for cells in ordered]
        run_ids = [run_id for _, _, _, (run_a, run_b) in per_period for run_id in (run_a, run_b)]
        book.add_table(
            f"{title}, {period.text}",
            TableValue(
                columns=table_columns,
                rows=ordered,
                rows_total=len(rows),
                sql=written_a.sql,
            ),
            proof=_proof(task, run_ids, metric, {}, period, None, "value"),
        )
    if len(periods) == 2:
        _save_new_movers(
            ctx, book, task, loaded, periods, per_period, title, metric, columns, width
        )


def _new_row_change(cells: list, compare_rows: dict, width: int):
    """One row's change and % change against the comparison period."""
    old = compare_rows.get(tuple(str(cell) for cell in cells[:width]))
    new = cells[width]
    if new is None or old is None:
        return None, None
    try:
        change = difference(new, old)
        percent = percent_change(new, old) if change is not None else None
        return change, percent
    except CalcError:
        return None, None


def _save_new_movers(
    ctx, book, task, loaded, periods, per_period, title, metric, columns, width
) -> None:
    """The biggest rises and falls, plus the grew/total counts."""
    main_rows = [[data_module._cell(value) for value in row] for row in per_period[0][0].rows]
    by_group = {data_module._group_key(row, width): row[width] for row in per_period[1][0].rows}
    moves: list[tuple] = []
    for row in data_module._ordered_rows(main_rows, width, None):
        old = by_group.get(data_module._group_key(row, width))
        new = row[width]
        if new is None or old is None:
            continue
        try:
            change = difference(new, old)
        except CalcError:
            continue
        if change is not None:
            moves.append((row, change))
    if not moves:
        return
    spans = [
        (task.split_by[pos] if pos < len(task.split_by) else columns[pos], pos, None)
        for pos in range(width)
    ]
    picked = sorted(moves, key=lambda item: item[1], reverse=True)[:6]
    for row, change in picked:
        name = data_module._group_display(row, spans)
        book.add_number(
            f"Change in {title} at {name}, {periods[0].text} vs {periods[1].text}",
            NumberValue(value=str(change), unit=NEW_UNIT, currency="", style="change"),
            proof=_proof(
                task,
                [],
                metric,
                data_module._group_ids(row, spans),
                periods[0],
                periods[1],
                "change",
            ),
        )
    grew = sum(1 for _, change in moves if change > 0)
    dim_title = loaded.titles.get(task.split_by[0], "rows") if task.split_by else "rows"
    for measure, count, desc, compare_period in (
        ("count_grew", grew, f"{dim_title} that grew", periods[1]),
        ("count_total", len(moves), f"{dim_title} in total", None),
    ):
        book.add_number(
            f"{desc}, {periods[0].text}"
            + (f" vs {compare_period.text}" if compare_period is not None else ""),
            NumberValue(value=str(count), unit="count", currency="", style="value"),
            proof=_proof(task, [], metric, {}, periods[0], compare_period, measure),
        )
    worst = min(moves, key=lambda item: item[1])
    if worst[1] < 0:
        name = data_module._group_display(worst[0], spans)
        ctx.log.add("found", f"Found: {grew} of {len(moves)} grew. The biggest drop is {name}.")
    else:
        best = max(moves, key=lambda item: item[1])
        name = data_module._group_display(best[0], spans)
        ctx.log.add("found", f"Found: {grew} of {len(moves)} grew. The biggest rise is {name}.")


def _maybe_add_todo(session, task: Task, ctx, description: str, first) -> None:
    """Offer an agreed number to the learner, once per description.

    Private runs (the hidden test set) never write learner todos.
    """
    if getattr(ctx, "private", False):
        return
    written_a, written_b, _, _ = first
    known = session.scalar(
        select(LearnerTodo.id).where(
            LearnerTodo.status == "open",
            LearnerTodo.kind == "new_metric",
            LearnerTodo.text_ == description,
        )
    )
    if known is not None:
        return
    add_learner_todo(
        session,
        kind="new_metric",
        text=description,
        details={
            "chat_id": ctx.chat_id,
            "message_id": ctx.message_id,
            "question": ctx.question,
            "sql_a": written_a.sql,
            "sql_b": written_b.sql,
        },
    )
