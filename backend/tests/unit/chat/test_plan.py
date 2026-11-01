"""The round planner picks follow-ups code can actually run (P10.9)."""

from types import SimpleNamespace

from charie.chat.analyst.plan import RoundPlan, _checked


def _loaded():
    return SimpleNamespace(
        usable={"orders"},
        dimensions={"dimension.status": {}, "dimension.month": {}},
    )


def _ctx():
    return SimpleNamespace(
        understanding=SimpleNamespace(filters=[]),
        periods=SimpleNamespace(periods=["p1", "p2"]),
    )


def _form(*tasks) -> RoundPlan:
    return RoundPlan.model_validate({"tasks": list(tasks)})


def _recipe(why="Get orders by status.", metric="orders", splits=None, top_n=None):
    return {
        "kind": "recipe",
        "metric_key": metric,
        "split_by": splits if splits is not None else ["dimension.status"],
        "top_n": top_n,
        "why": why,
    }


def test_plan_parses_chosen_tasks_with_rewritten_whys() -> None:
    """Chosen tasks keep their rewritten whys and run against every period."""
    picked = _checked(_loaded(), _ctx(), _form(_recipe(why="Get orders by status.")), [])
    assert len(picked) == 1
    assert picked[0].kind == "recipe"
    assert picked[0].why == "Get orders by status."
    assert picked[0].periods == ["p1", "p2"]


def test_plan_skips_excluded_and_unknown_recipes() -> None:
    """Excluded or unknown metric keys never become tasks."""
    picked = _checked(
        _loaded(),
        _ctx(),
        _form(
            _recipe(metric="net_sales"),
            _recipe(metric="unknown_metric"),
            _recipe(),
        ),
        [],
    )
    assert [task.metric_key for task in picked] == ["orders"]


def test_plan_drops_digit_whys_and_empty_picks() -> None:
    """Whys with numbers and empty words never become tasks."""
    picked = _checked(
        _loaded(),
        _ctx(),
        _form(
            _recipe(why="Get top 5 orders."),
            {"kind": "new_number", "new_metric": "", "why": "Work out a number."},
            {"kind": "documents", "search": "", "why": "Look through the documents."},
            _recipe(why=""),
        ),
        [],
    )
    assert picked == []


def test_plan_drops_unknown_splits_and_caps_tasks() -> None:
    """Unknown splits fall off; at most 4 picks run, and only once each."""
    form = _form(
        _recipe(why="Get orders by status and month."),
        _recipe(why="Get orders by status.", splits=["dimension.status"]),
        _recipe(why="Get orders by month.", splits=["dimension.month"]),
        _recipe(why="Get all orders.", splits=[]),
        _recipe(why="Get the top orders.", splits=[], top_n=3),
    )
    form.tasks[0].split_by = ["dimension.unknown", "dimension.status", "dimension.month"]
    picked = _checked(_loaded(), _ctx(), form, [])
    assert len(picked) == 4
    assert picked[0].split_by == ["dimension.status", "dimension.month"]
    again = _checked(_loaded(), _ctx(), form, picked)
    assert again == []


def test_new_number_and_documents_picks_keep_their_fields() -> None:
    """Words and searches survive; the question's filters apply."""
    picked = _checked(
        _loaded(),
        _ctx(),
        _form(
            {
                "kind": "new_number",
                "new_metric": "How many shop orders are there?",
                "why": "Work out a number.",
            },
            {"kind": "documents", "search": "net sales", "why": "Look through the documents."},
        ),
        [],
    )
    assert [(task.kind, task.new_metric or task.search) for task in picked] == [
        ("new_number", "How many shop orders are there?"),
        ("documents", "net sales"),
    ]
    assert all(task.filters == [] for task in picked)
