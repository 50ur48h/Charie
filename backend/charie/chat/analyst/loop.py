"""The round loop: starter tasks, then planned follow-ups, until enough (P10.9).

One question runs at most 4 rounds. Round 1 runs the starter tasks as
they are; later rounds ask the planner for new tasks only. Every round
runs its tasks at the same time, then the enough check decides. When
the planner returns nothing new, the round still runs (with zero tasks)
and the check still decides.
"""

import asyncio

from charie.chat.analyst.enough import run_check_enough
from charie.chat.analyst.helpers.data import add_period_items, run_recipe_task
from charie.chat.analyst.helpers.documents import run_document_task
from charie.chat.analyst.helpers.new_number import run_new_number_task
from charie.chat.analyst.helpers.tasks import Task, starter_tasks
from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.notebook import FindingValue, Notebook
from charie.chat.analyst.plan import plan_round
from charie.chat.analyst.understand import understand
from charie.shared.ai.errors import AiError
from charie.shared.db import session_scope

MAX_ROUNDS = 4


async def run_rounds(ctx) -> list[Task]:
    """Understand once, run up to 4 rounds; returns every task run, in order."""
    understand(ctx)
    if ctx.state.finish_requested.is_set():
        _remember_stop(ctx, "finished", "")
        return []
    add_period_items(ctx)
    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
    planned = starter_tasks(ctx.understanding, kb.titles())
    ran: list[Task] = []
    current = list(planned)
    missing = ""
    for round_no in range(1, MAX_ROUNDS + 1):
        if ctx.state.finish_requested.is_set():
            break
        seq = _start_round(ctx, current, round_no)
        await _run_tasks(current, ctx, round_no)
        ran.extend(current)
        missing = run_check_enough(ctx, round_no)
        _finish_round(ctx, seq, current, round_no, missing)
        if not missing:
            break
        current = [task for task in _next_tasks(ctx, planned, round_no + 1) if task not in ran]
        planned.extend(current)
    if ctx.state.finish_requested.is_set():
        _remember_stop(ctx, "finished", missing)
    elif missing:
        _remember_stop(ctx, "rounds_done", missing)
    else:
        _remember_stop(ctx, "answered", "")
    return ran


async def run_extra_round(ctx, ran: list[Task], round_no: int, focus: str) -> list[Task]:
    """One more round after the loop, guided by the reviewer's focus."""
    current = [
        task for task in plan_round(ctx, ran, ctx.question, round_no, focus) if task not in ran
    ]
    seq = _start_round(ctx, current, round_no)
    await _run_tasks(current, ctx, round_no)
    missing = run_check_enough(ctx, round_no)
    _finish_round(ctx, seq, current, round_no, missing)
    _remember_stop(ctx, "rounds_done", missing)
    return current


def _remember_stop(ctx, reason: str, missing: str) -> None:
    """What the writer needs: why the rounds stopped and what is still open."""
    ctx.stop_reason = reason
    ctx.still_open = [missing] if missing else []
    with session_scope() as session:
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        ctx.cannot_tell = [
            FindingValue.model_validate(item.value).text
            for item in book.items()
            if item.kind == "finding"
            and FindingValue.model_validate(item.value).type in ("nothing_found", "couldnt_check")
        ]


def _start_round(ctx, current: list[Task], round_no: int) -> int:
    """The step line: this round's tasks in the panel's words."""
    if current:
        title = f"Round {round_no}: {current[0].why}"
        body = "\n".join(task.why for task in current)
    else:
        title = f"Round {round_no}: no new tasks."
        body = "No new tasks this round."
    return ctx.log.start("step", title, body)


def _finish_round(ctx, seq: int, current: list[Task], round_no: int, missing: str) -> None:
    """The done line: answered, still missing, or nothing new."""
    if not current:
        title = f"Round {round_no} done: no new tasks, so no new answers."
    elif missing:
        title = f"Round {round_no} done: still needs {missing}."
    else:
        title = f"Round {round_no} done: the question is answered."
    ctx.log.finish(seq, status="done", title=title)


def _next_tasks(ctx, planned: list[Task], round_no: int) -> list[Task]:
    """The planner's new picks; a broken planner simply picks nothing."""
    try:
        return plan_round(ctx, planned, ctx.question, round_no)
    except AiError:
        return []


async def _run_tasks(tasks: list[Task], ctx, round_no: int) -> None:
    """Every task on the round, at the same time, labeled with the round."""
    if not tasks:
        return
    gate = asyncio.Semaphore(4)

    async def _one(task: Task) -> None:
        async with gate:
            if task.kind == "new_number":
                await asyncio.to_thread(run_new_number_task, task, ctx, round_no)
            elif task.kind == "documents":
                await asyncio.to_thread(run_document_task, task, ctx, round_no)
            else:
                await asyncio.to_thread(run_recipe_task, task, ctx, round_no)

    await asyncio.gather(*(_one(task) for task in tasks))
