"""The round planner: which follow-up tasks to run (P10.9).

Round 1 runs the starter tasks as they are. Later rounds ask the AI to
pick follow-ups; code checks every pick (known usable recipes, words
for new numbers, a search for documents, plain whys) and only runs
tasks it has not run before.
"""

from typing import Literal

from pydantic import BaseModel, Field

from charie.chat.analyst.helpers.data import _Loaded
from charie.chat.analyst.helpers.tasks import Task, task_signature
from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.understand import knowledge_summary
from charie.shared.ai.client import get_ai
from charie.shared.db import session_scope

JOB_KIND = "plan_round"
MAX_TASKS_PER_ROUND = 4


class PlannedTask(BaseModel):
    """One follow-up the AI picks; code fills periods and filters."""

    kind: Literal["recipe", "new_number", "documents"] = Field(
        description="The task kind, one per kind."
    )
    metric_key: str = Field(default="", description="The usable recipe key.")
    new_metric: str = Field(default="", description="The new number in words.")
    search: str = Field(default="", description="The document search phrase.")
    split_by: list[str] = Field(default=[], description="Known dimension keys.")
    top_n: int | None = Field(default=None, description="Keep this many rows.")
    why: str = Field(default="", description="Plain short words, no numbers.")


class RoundPlan(BaseModel):
    """The AI's follow-up picks for one round."""

    tasks: list[PlannedTask] = Field(default=[], description="At most 4 picks.")


def _has_digits(text: str) -> bool:
    """A rewritten why names no number."""
    return any(char.isdigit() for char in text)


def plan_round(ctx, tasks: list[Task], question: str, round_no: int) -> list[Task]:
    """The follow-up tasks for one round: asked, checked, and new only."""
    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
        loaded = _Loaded(session, ctx.kb_version_id)
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        done = "\n".join(f"[{item.label}] {item.description}" for item in book.items())
        usable = sorted(f"{key}: {loaded.recipe_title(key)}" for key in loaded.usable)
        summary = knowledge_summary(kb)
    form = get_ai().run(
        JOB_KIND,
        {
            "question": question,
            "month": ctx.periods.periods[0].text if ctx.periods.periods else "",
            "done": done or "none yet",
            "round": round_no,
            "starter": "\n".join(f"{task.kind}: {task.why}" for task in tasks),
            "usable": "\n".join(usable),
        },
        RoundPlan,
        app="chat",
        message_id=ctx.message_id,
        knowledge_summary=summary,
        already_running=True,
    )
    with session_scope() as session:
        loaded = _Loaded(session, ctx.kb_version_id)
        return _checked(loaded, ctx, form, tasks)


def _checked(loaded: _Loaded, ctx, form: RoundPlan, tasks: list[Task]) -> list[Task]:
    """The picks code can run: known fields, plain whys, never run before."""
    seen = {task_signature(task) for task in tasks}
    picked: list[Task] = []
    labels = [f"p{num}" for num in range(1, len(ctx.periods.periods) + 1)]
    for planned in form.tasks[:MAX_TASKS_PER_ROUND]:
        if not planned.why or _has_digits(planned.why):
            continue
        splits = [key for key in planned.split_by if key in loaded.dimensions]
        top_n = planned.top_n if isinstance(planned.top_n, int) and planned.top_n > 0 else None
        try:
            task = _planned_task(planned, splits, top_n, ctx, labels, loaded)
        except Exception:  # noqa: BLE001 (a malformed pick is skipped, not run)
            continue
        signature = task_signature(task)
        if signature in seen:
            continue
        seen.add(signature)
        picked.append(task)
    return picked


def _planned_task(planned: PlannedTask, splits: list, top_n, ctx, labels, loaded) -> Task:
    """One pick as a runnable task; unknown or excluded picks raise."""
    if planned.kind == "recipe":
        if planned.metric_key not in loaded.usable:
            raise ValueError(f"Recipe {planned.metric_key} is unknown or excluded.")
        return Task(
            kind="recipe",
            why=planned.why,
            metric_key=planned.metric_key,
            split_by=splits,
            filters=list(ctx.understanding.filters),
            periods=labels[:3],
            top_n=top_n,
        )
    if planned.kind == "new_number":
        if not planned.new_metric.strip():
            raise ValueError("A new-number pick needs words.")
        return Task(
            kind="new_number",
            why=planned.why,
            new_metric=planned.new_metric,
            split_by=splits,
            filters=list(ctx.understanding.filters),
            periods=labels[:3],
            top_n=top_n,
        )
    if not planned.search.strip():
        raise ValueError("A documents pick needs a search.")
    return Task(
        kind="documents",
        why=planned.why,
        search=planned.search,
        split_by=splits,
        filters=list(ctx.understanding.filters),
    )
