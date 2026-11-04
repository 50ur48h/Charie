"""What a run may spend, and what happens when it has spent it (architecture 4.4)."""

from __future__ import annotations

from charie.agent.budget import (
    DEFAULT_ITERATIONS,
    DEFAULT_LLM_CALLS,
    DEFAULT_QUERIES,
    DEFAULT_TOKENS,
    DEFAULT_WALL_SECONDS,
    MAX_OVERRIDES,
    Budget,
    BudgetState,
)


def test_the_defaults_are_the_numbers_the_architecture_names() -> None:
    """4.4 gives five figures. A drift here is a change to the product's cost profile."""
    budget = Budget()

    assert (budget.iterations, budget.queries, budget.llm_calls) == (12, 14, 32)
    assert budget.tokens == 225_000
    assert budget.wall_seconds == 330.0
    assert (DEFAULT_ITERATIONS, DEFAULT_QUERIES, DEFAULT_LLM_CALLS) == (12, 14, 32)
    assert (DEFAULT_TOKENS, DEFAULT_WALL_SECONDS) == (225_000, 330.0)


def test_the_call_ceiling_fits_the_run_that_spends_the_most() -> None:
    """The two ceilings have to agree, and this is the arithmetic that says so."""
    per_iteration = 2  # plan, then reflect
    composes = 2  # the second is the critic's one bounded re-entry
    critics = 2  # one verdict per composed draft
    intake = 1  # 4.4 names it; not built yet, and counted anyway

    worst = DEFAULT_ITERATIONS * per_iteration + composes + critics + intake

    assert worst <= DEFAULT_LLM_CALLS, (
        f"a full run needs {worst} calls against a ceiling of {DEFAULT_LLM_CALLS}; "
        "raise the ceiling or take a stage out"
    )


def test_an_organization_may_lower_a_ceiling_freely() -> None:
    """A tenant that wants cheaper answers should get them."""
    budget = Budget.from_overrides({"iterations": 3, "queries": 2})

    assert budget.iterations == 3
    assert budget.queries == 2
    assert budget.llm_calls == DEFAULT_LLM_CALLS, "untouched dimensions keep their default"


def test_raising_a_ceiling_is_clamped_rather_than_refused() -> None:
    """The whole point of a hard cap is that no configuration turns it off."""
    budget = Budget.from_overrides({"iterations": 10_000, "wall_seconds": 99_999})

    assert budget.iterations == MAX_OVERRIDES["iterations"]
    assert budget.wall_seconds == MAX_OVERRIDES["wall_seconds"]


def test_a_typo_in_configuration_does_not_stop_a_run() -> None:
    """Unknown keys and unusable values are ignored, not raised on: this is configuration."""
    budget = Budget.from_overrides(
        {"iterations": "lots", "quries": 4, "queries": 0, "llm_calls": -3, "tokens": True}
    )

    assert budget == Budget(), "nothing usable was supplied, so nothing changed"


def test_nothing_configured_is_the_default() -> None:
    assert Budget.from_overrides(None) == Budget()
    assert Budget.from_overrides({}) == Budget()


# --- Spending it ---


def test_a_fresh_run_has_not_exhausted_anything() -> None:
    state = BudgetState(budget=Budget())

    assert state.exhausted(now=state.started_at) is None


def _stopped_by(state: BudgetState) -> str | None:
    found = state.exhausted(now=state.started_at)
    return None if found is None else found.dimension


def test_iterations_stop_the_run_on_their_own() -> None:
    """Each dimension is checked separately because each is a different way to run away."""
    state = BudgetState(budget=Budget())
    for _ in range(DEFAULT_ITERATIONS):
        state.spend_iteration()

    assert _stopped_by(state) == "iterations"


def test_queries_stop_the_run_on_their_own() -> None:
    state = BudgetState(budget=Budget())
    for _ in range(DEFAULT_QUERIES):
        state.spend_query()

    assert _stopped_by(state) == "queries"


def test_model_calls_stop_the_run_on_their_own() -> None:
    state = BudgetState(budget=Budget())
    for _ in range(DEFAULT_LLM_CALLS):
        state.spend_llm()

    assert _stopped_by(state) == "llm_calls"


def test_tokens_stop_the_run_even_when_few_calls_were_made() -> None:
    """One enormous call can exhaust the reading budget without going near the call ceiling."""
    state = BudgetState(budget=Budget())
    state.spend_llm(DEFAULT_TOKENS)

    assert _stopped_by(state) == "tokens"
    assert state.llm_calls == 1


def test_time_is_reported_before_any_other_ceiling() -> None:
    """Deliberate ordering: wall clock is the one the person waiting feels."""
    state = BudgetState(budget=Budget())
    for _ in range(DEFAULT_ITERATIONS):
        state.spend_iteration()

    found = state.exhausted(now=state.started_at + DEFAULT_WALL_SECONDS + 1)

    assert found is not None
    assert found.dimension == "wall_seconds"


def test_exhaustion_reads_as_something_a_person_asked_for() -> None:
    """The caveat on a partial answer is read by whoever asked the question."""
    state = BudgetState(budget=Budget())
    for _ in range(DEFAULT_LLM_CALLS):
        state.spend_llm()

    found = state.exhausted(now=state.started_at)

    assert found is not None
    assert "reasoning" in found.reason
    assert "llm_calls" not in found.reason


def test_a_model_call_spends_its_tokens_too() -> None:
    """Counted together because they are always spent together."""
    state = BudgetState(budget=Budget())

    state.spend_llm(1_200)

    assert state.llm_calls == 1
    assert state.tokens == 1_200


def test_a_warning_fires_once_per_dimension() -> None:
    """A trace should show the run tightening."""
    state = BudgetState(budget=Budget(iterations=4))
    for _ in range(3):
        state.spend_iteration()

    assert state.approaching(now=state.started_at) == "iterations"
    assert state.approaching(now=state.started_at) is None, "said once"


def test_a_run_well_inside_its_budget_warns_about_nothing() -> None:
    state = BudgetState(budget=Budget())
    state.spend_iteration()

    assert state.approaching(now=state.started_at) is None


def test_the_allowance_is_recorded_with_what_was_spent() -> None:
    """`agent_runs.budget` keeps the ceilings this run was given."""
    state = BudgetState(budget=Budget(iterations=5))
    state.spend_iteration()
    state.spend_query()
    state.spend_llm(700)

    recorded = state.as_json()

    assert recorded["iterations"] == 1
    assert recorded["queries"] == 1
    assert recorded["tokens"] == 700
    assert recorded["limits"] == Budget(iterations=5).as_json()
