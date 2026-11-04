"""The engine trial's comparison, and the floor under it."""

from __future__ import annotations

import uuid

import pytest

from charie.agent.state import ResearchState
from charie.ops import trial


def _run(
    *,
    status: str = "completed",
    state: str = "answered",
    unanswered: str = "",
    answer: str = "There are 3 shops.",
    tables: tuple[str, ...] = ("public.shops",),
    statements: tuple[str, ...] = ("SELECT count(*) FROM shops",),
) -> trial.ProbeRun:
    return trial.ProbeRun(
        run_id=uuid.uuid4(),
        status=status,
        state=state,
        unanswered=unanswered,
        answer=answer,
        sources_offered=(),
        tables_read=tables,
        statements=statements,
        limitations=(),
        method="1 query over one step",
        findings=1,
    )


# --- The control comes first, because everything below is worthless without it ---


def test_three_identical_runs_disagree_about_nothing() -> None:
    """A comparison that flags agreement flags everything."""
    assert trial.divergences(tuple(_run() for _ in range(3))) == ()


# --- The two shapes this tool exists to catch ---


def test_a_question_that_refuses_once_and_answers_twice_is_flagged() -> None:
    """B-119's shape, and the reason for the repeat floor."""
    found = trial.divergences(
        (_run(), _run(), _run(state="refused", answer="I could not answer that."))
    )

    assert any("ended differently" in note for note in found)
    assert any("B-119" in note for note in found)


def test_runs_that_read_different_tables_are_flagged() -> None:
    """B-060's shape: two defensible sources for one question."""
    found = trial.divergences(
        (
            _run(tables=("public.fact_sale",)),
            _run(tables=("public.fact_sale",)),
            _run(tables=("public.fact_purchase",)),
        )
    )

    assert any("different tables" in note for note in found)
    assert any("B-060" in note for note in found)


def test_runs_that_state_different_numbers_are_flagged() -> None:
    found = trial.divergences(
        (_run(answer="Revenue was 1,735,835.05."), _run(answer="Revenue was 3,625,180.34."))
    )

    assert any("different numbers" in note for note in found)


def test_the_same_number_written_differently_is_not_a_disagreement() -> None:
    """Thousands separators are formatting, not a different answer."""
    assert trial.divergences((_run(answer="1,735,835.05"), _run(answer="1735835.05"))) == ()


# --- The floor ---


@pytest.mark.asyncio
async def test_a_single_run_is_refused_with_the_reason() -> None:
    """`MINIMUM_REPEATS` is enforced, not defaulted."""
    with pytest.raises(ValueError, match="B-119"):
        await trial.run_probe(
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            data_source_id=uuid.uuid4(),
            question="anything",
            repeats=1,
        )


# --- The correspondence check — the one that catches this module's own defect class ---


def test_the_state_key_this_reads_is_the_key_the_agent_writes() -> None:
    """Written after getting it wrong."""
    state = ResearchState(
        run_id=uuid.uuid4(), org_id=uuid.uuid4(), question="which outlet wastes the most?"
    )
    state.candidate_sources = ["public.fact_waste", "public.fact_sale"]

    stored = state.as_json()

    assert "candidate_sources" in stored, (
        "the agent no longer records candidate_sources under that key, so the trial "
        "report's 'sources offered' column is silently empty"
    )
    assert trial.offered_sources(stored) == ["public.fact_sale", "public.fact_waste"]


def test_offered_sources_survives_a_run_that_recorded_nothing() -> None:
    """A run that refused before context was built has no candidates."""
    assert trial.offered_sources(None) == []
    assert trial.offered_sources({}) == []
    assert trial.offered_sources({"candidate_sources": "not a list"}) == []
