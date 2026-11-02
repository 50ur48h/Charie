"""Unit tests for the F2/F4 loop helpers: why top-up, not-in-data numbers, stall signature."""

from types import SimpleNamespace

from charie.chat.analyst.helpers.tasks import Task
from charie.chat.analyst.loop import (
    _not_in_data_start,
    _top_up_why,
    evidence_signature,
)


def _ctx(kind="why", periods=2, topics=None):
    return SimpleNamespace(
        understanding=SimpleNamespace(
            kind=kind,
            filters=[],
            document_topics=list(topics or []),
        ),
        periods=SimpleNamespace(periods=["p1", "p2"][:periods]),
        question="Why did net sales grow from 2024 to 2025?",
    )


def _item(label, kind="number", status="ok", description="Some number"):
    return SimpleNamespace(label=label, kind=kind, status=status, description=description)


def test_top_up_adds_number_task_for_why() -> None:
    """A two-period why with only document starters gets a worked number task."""
    planned = [Task(kind="documents", why="Look through the documents.", search="net sales")]
    topped = _top_up_why(_ctx(topics=["net sales"]), planned)
    assert len(topped) == 2
    assert topped[1].kind == "new_number"
    assert topped[1].new_metric == "net sales"
    assert topped[1].periods == ["p1", "p2"]


def test_top_up_keeps_existing_number_tasks() -> None:
    """A why that already fetches numbers is left alone."""
    planned = [Task(kind="recipe", metric_key="m", periods=["p1", "p2"])]
    assert _top_up_why(_ctx(), planned) == planned


def test_top_up_ignores_other_kinds() -> None:
    """Clear questions keep today's starter tasks."""
    planned = [Task(kind="documents", why="Look through the documents.", search="x")]
    assert _top_up_why(_ctx(kind="clear"), planned) == planned


def test_not_in_data_with_periods_fetches_numbers() -> None:
    """Periods plus topics mean worked numbers, not a single doc task."""
    tasks = _not_in_data_start(_ctx(kind="not_in_data", topics=["net sales"]))
    assert tasks is not None
    assert [task.kind for task in tasks] == ["new_number"]
    assert tasks[0].new_metric == "net sales"


def test_not_in_data_without_periods_stays_documents() -> None:
    """No periods means the single document task, as today."""
    assert _not_in_data_start(_ctx(kind="not_in_data", periods=0, topics=["x"])) is None


def test_not_in_data_without_topics_stays_documents() -> None:
    """Periods with nothing to work out mean the single document task."""
    assert _not_in_data_start(_ctx(kind="not_in_data", topics=[])) is None


def test_evidence_signature_moves_with_new_items() -> None:
    """A new notebook item changes the signature; a repeat read does not."""
    before = evidence_signature([_item("p1", kind="period", description="in December")])
    same = evidence_signature([_item("p1", kind="period", description="in December")])
    after = evidence_signature([_item("p1", kind="period", description="in December"), _item("n1")])
    assert before == same
    assert before != after


def _full_item(label, kind="finding", description="Nothing found.", value=None, proof=None):
    from types import SimpleNamespace as NS

    return NS(
        label=label,
        kind=kind,
        status="ok",
        description=description,
        value=value if value is not None else {"text": description},
        proof=proof if proof is not None else {"task": "documents|x"},
    )


def test_duplicate_findings_share_one_signature() -> None:
    """Review finding: a re-added finding is the same evidence twice."""
    from charie.chat.analyst.loop import evidence_signature

    first = [_full_item("q1")]
    again = [_full_item("q1"), _full_item("q2")]
    assert evidence_signature(first) == evidence_signature(again)


def test_period_cards_are_trace_not_evidence() -> None:
    """Review finding: period cards never count as new evidence."""
    from charie.chat.analyst.loop import evidence_signature

    assert evidence_signature([_item("p1", kind="period")]) == evidence_signature([])
    assert evidence_signature([_item("p1", kind="period")]) != evidence_signature([_item("n1")])


def test_values_and_provenance_count() -> None:
    """Review finding: changed numbers and sources change the signature."""
    from charie.chat.analyst.loop import evidence_signature

    base = [_full_item("n1", kind="number", value={"value": "5"}, proof={"recipe_key": "m"})]
    changed_value = [
        _full_item("n1", kind="number", value={"value": "6"}, proof={"recipe_key": "m"})
    ]
    changed_source = [
        _full_item("n1", kind="number", value={"value": "5"}, proof={"recipe_key": "other"})
    ]
    assert evidence_signature(base) != evidence_signature(changed_value)
    assert evidence_signature(base) != evidence_signature(changed_source)
