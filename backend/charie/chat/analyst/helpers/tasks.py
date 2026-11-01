"""One question's data tasks: what to get with a recipe (P10.6).

A task names a recipe, splits, filters and periods. Code builds the
query from the recipe, checks it, runs it read-only, and puts labelled
numbers and tables in the notebook.
"""

from typing import Literal

from pydantic import BaseModel, Field

from charie.chat.analyst.understand import Filter, Understanding

#: At most this many recipe tasks run for one question.
MAX_TASKS = 4


class Task(BaseModel):
    """One fetch: a recipe, a new number or documents (reused by `plan_round`)."""

    kind: Literal["recipe", "new_number", "documents"] = Field(description="What to fetch.")
    why: str = Field(default="", description="One line for the thinking panel, no digits.")
    metric_key: str = Field(default="", description="The recipe key, for recipe tasks.")
    new_metric: str = Field(default="", description="Plain words, for new-number tasks.")
    split_by: list[str] = Field(default=[], description="Up to 2 dimension keys.")
    filters: list[Filter] = Field(default=[], description="The filters to apply.")
    periods: list[str] = Field(default=[], description="Period labels like p1, at most 3.")
    top_n: int | None = Field(default=None, description="Keep the top rows, or empty.")
    search: str = Field(default="", description="The search phrase, for document tasks.")


def task_signature(task: Task) -> str:
    """One stable string per task: the kind, the key, sorted everything else."""
    key = task.metric_key or task.new_metric or task.search
    filters = sorted(
        f"{filt.dimension_key}:{','.join(sorted(str(value) for value in filt.values))}"
        for filt in task.filters
    )
    parts = [task.kind, key, *sorted(task.split_by), *filters, *sorted(task.periods)]
    if task.top_n is not None:
        parts.append(f"top_{task.top_n}")
    return "|".join(parts)


def _why(title: str, split_titles: list[str], period_count: int) -> str:
    """One line with no digits: what to get, and how many periods."""
    words = {1: "the period", 2: "both periods"}.get(period_count, "each period")
    if split_titles:
        return f"Get {title} by {' and '.join(split_titles)} for {words}."
    return f"Get {title} for {words}."


def starter_tasks(understanding: Understanding, titles: dict[str, str]) -> list[Task]:
    """One recipe task per asked metric, over every period, at most 4."""
    labels = [f"p{num}" for num in range(1, len(understanding.periods) + 1)]
    tasks: list[Task] = []
    for ask in understanding.asks:
        if not ask.metric_key or len(tasks) >= MAX_TASKS:
            continue
        split_titles = [titles.get(key, key) for key in ask.split_by]
        tasks.append(
            Task(
                kind="recipe",
                why=_why(titles.get(ask.metric_key, ask.metric_key), split_titles, len(labels)),
                metric_key=ask.metric_key,
                split_by=list(ask.split_by),
                filters=list(understanding.filters),
                periods=labels[:3],
                top_n=ask.top_n,
            )
        )
    return tasks
