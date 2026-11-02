"""Starter tasks: recipe tasks per metric, new-number tasks per words (P10.6, P10.7).

F1: an ask whose recipe contradicts a documented business term is dropped
with a note, so gross can never answer for net (B020).
"""

from types import SimpleNamespace

from charie.chat.analyst.dates import PeriodExpression
from charie.chat.analyst.helpers.tasks import MAX_TASKS, Task, starter_tasks, task_signature
from charie.chat.analyst.understand import Ask, Filter, Understanding


def _understanding(asks=1, periods=1) -> Understanding:
    return Understanding(
        kind="clear",
        reading="I read this as sales for [p1].",
        periods=[PeriodExpression(kind="month", number=12) for _ in range(periods)],
        asks=[Ask(metric_key=f"metric_{n}") for n in range(asks)],
        filters=[Filter(dimension_key="dim", values=["Downtown"])],
        defaults_used=[],
        document_topics=[],
    )


def _kb() -> SimpleNamespace:
    titles = {f"metric_{n}": f"Metric {n}" for n in range(6)}
    titles["metric.delivered_order_amount"] = "Delivered order amount"
    titles["metric.delivered_orders"] = "Delivered orders"
    return SimpleNamespace(
        titles=lambda: titles,
        meanings=lambda: {
            "metric.delivered_order_amount": "Total amount for delivered orders.",
            "metric.delivered_orders": "Number of delivered orders for an outlet.",
        },
        metrics=lambda: {
            "metric.delivered_order_amount": {"unit": "money"},
            "metric.delivered_orders": {"unit": "count"},
        },
    )


def _started(understanding, question=""):
    tasks, dropped = starter_tasks(understanding, _kb(), question)
    return tasks, dropped


def test_starter_tasks_one_per_metric_ask() -> None:
    """Each asked metric becomes one recipe task over every period."""
    tasks, dropped = _started(_understanding(asks=2, periods=2))
    assert len(tasks) == 2
    assert all(task.kind == "recipe" for task in tasks)
    assert [task.metric_key for task in tasks] == ["metric_0", "metric_1"]
    assert all(task.periods == ["p1", "p2"] for task in tasks)
    assert all(len(task.filters) == 1 for task in tasks)
    assert dropped == []


def test_starter_tasks_makes_new_number_tasks() -> None:
    """Asks in plain words become new-number tasks with digit-free lines."""
    understanding = _understanding()
    understanding.asks = [Ask(new_metric="something new")]
    tasks, dropped = _started(understanding)
    assert len(tasks) == 1
    assert tasks[0].kind == "new_number"
    assert tasks[0].new_metric == "something new"
    assert tasks[0].periods == ["p1"]
    assert not any(char.isdigit() for char in tasks[0].why)
    assert dropped == []


def test_starter_tasks_makes_document_tasks_first() -> None:
    """Document topics come first and share the 4-task cap."""
    understanding = _understanding(asks=0, periods=1)
    understanding.document_topics = ["net sales", "checkout code", "prices", "profit", "extra"]
    understanding.asks = [Ask(metric_key="metric_0")]
    tasks, dropped = _started(understanding)
    assert [task.kind for task in tasks] == ["documents"] * 4
    assert tasks[0].search == "net sales"
    assert dropped == []


def test_starter_tasks_mixes_recipes_and_new_numbers() -> None:
    """Recipe and new-number asks share the 4-task cap in order."""
    understanding = _understanding(asks=0, periods=2)
    understanding.asks = [
        Ask(metric_key="metric_0"),
        Ask(new_metric="something new"),
        Ask(metric_key="metric_1"),
    ]
    tasks, dropped = _started(understanding)
    assert [task.kind for task in tasks] == ["recipe", "new_number", "recipe"]
    assert all(task.periods == ["p1", "p2"] for task in tasks)
    assert dropped == []


def test_starter_tasks_at_most_four() -> None:
    """Six asked metrics still give four tasks."""
    tasks, dropped = _started(_understanding(asks=6))
    assert len(tasks) == MAX_TASKS == 4
    assert dropped == []


def test_starter_tasks_drops_net_sales_gross_recipe() -> None:
    """The pilot failure: net sales never runs the delivered-amount recipe."""
    understanding = _understanding(asks=0, periods=1)
    understanding.asks = [
        Ask(metric_key="metric.delivered_orders"),
        Ask(metric_key="metric.delivered_order_amount"),
    ]
    tasks, dropped = _started(
        understanding,
        "How many orders did we have in December 2025, and what were net sales?",
    )
    assert [task.metric_key for task in tasks] == ["metric.delivered_orders"]
    assert len(dropped) == 1
    assert "metric.delivered_order_amount" in dropped[0]
    assert "net sales" in dropped[0]


def test_starter_tasks_keeps_gross_without_house_term() -> None:
    """No documented term in the question: the recipe still runs."""
    understanding = _understanding(asks=0, periods=1)
    understanding.asks = [Ask(metric_key="metric.delivered_order_amount")]
    tasks, dropped = _started(understanding, "How much did we sell in December?")
    assert [task.metric_key for task in tasks] == ["metric.delivered_order_amount"]
    assert dropped == []


def test_task_signature_ignores_order() -> None:
    """Sorted splits, filters and periods give one stable signature."""
    first = Task(
        kind="recipe",
        metric_key="m",
        split_by=["b", "a"],
        filters=[Filter(dimension_key="d", values=["y", "x"])],
        periods=["p2", "p1"],
    )
    second = Task(
        kind="recipe",
        metric_key="m",
        split_by=["a", "b"],
        filters=[Filter(dimension_key="d", values=["x", "y"])],
        periods=["p1", "p2"],
    )
    assert task_signature(first) == task_signature(second)
    assert task_signature(first) != task_signature(Task(kind="recipe", metric_key="other"))
