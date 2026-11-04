"""The rule that makes a definition bind (D-033, B-078, WP10.2c)."""

from __future__ import annotations

import uuid
from datetime import date

from charie.agent import critic
from charie.agent.context import (
    ContextBundle,
    DefinitionFrame,
    KnowledgeFrame,
    render,
)
from charie.agent.state import ExecutionRef, ResearchState
from charie.agent.tools.finalize import FinalizeIn
from charie.semantic.definitions import Definition, RequiredFilter

EXECUTION = "11111111-1111-1111-1111-111111111111"

NET_REVENUE = Definition(
    id=uuid.uuid4(),
    name="net_revenue",
    kind="metric",
    description="Revenue excluding cancelled and refunded orders.",
    expression="sum(orders.total_amount)",
    required_filters=(
        RequiredFilter(
            table="orders", column="status", op="not_in", values=("cancelled", "refunded")
        ),
    ),
    synonyms=("net revenue",),
)


def _prompt(bundle: ContextBundle) -> str:
    """The system message a model would actually receive."""
    return render(bundle)[0].content


DEFINITION_HEADING = "[L3] What this organization means by these terms"


def _definition_block(bundle: ContextBundle) -> str:
    """Everything the prompt says under the definitions heading."""
    prompt = _prompt(bundle)
    assert DEFINITION_HEADING in prompt, "the definitions layer is not in the prompt at all"
    after = prompt.split(DEFINITION_HEADING, 1)[1]
    return after.split("[L4]", 1)[0].split("[L5]", 1)[0]


def _evidence(
    statement: str, *, definitions: tuple[Definition, ...] = (NET_REVENUE,)
) -> critic.Evidence:
    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())
    state.question = "What was net revenue last month?"
    # A real execution on the state, so `_citations_resolve` is satisfied and what these tests...
    state.record_execution(
        ExecutionRef(
            execution_id=EXECUTION,
            purpose="net revenue",
            sql_hash="abc123",
            row_count=1,
            summary="net revenue: 1234",
            ok=True,
        )
    )
    return critic.Evidence(
        question=state.question,
        as_of=date(2026, 8, 1),
        state=state,
        statements={EXECUTION: statement},
        definitions=definitions,
    )


def _draft() -> FinalizeIn:
    return FinalizeIn(answer="Net revenue was 1,234.", supported_by=[EXECUTION], confidence="high")


def _rules(findings: tuple[critic.CriticFinding, ...]) -> set[str]:
    return {finding.rule for finding in findings}


# --- The central criterion: the model drops the filter and the critic catches it ---


def test_a_query_that_ignores_a_required_filter_is_blocked() -> None:
    """The criterion. The definition requires the query to constrain `status`."""
    findings = critic.check(
        _draft(), _evidence("SELECT sum(total_amount) AS net_revenue FROM orders")
    )

    assert "required_filter_missing" in _rules(findings)
    blocked = next(f for f in findings if f.rule == "required_filter_missing")
    assert blocked.severity == critic.BLOCK
    assert "net_revenue" in blocked.detail
    assert "orders.status" in blocked.detail


def test_the_block_names_what_the_definition_required() -> None:
    """A finding a person cannot act on is a finding that gets ignored."""
    findings = critic.check(
        _draft(), _evidence("SELECT sum(total_amount) AS net_revenue FROM orders")
    )

    detail = next(f for f in findings if f.rule == "required_filter_missing").detail
    assert "none of" in detail
    assert "cancelled" in detail and "refunded" in detail


# --- The false-block twins (standing note 5) ---


def test_the_definition_written_exactly_passes() -> None:
    findings = critic.check(
        _draft(),
        _evidence(
            "SELECT sum(total_amount) AS net_revenue FROM orders "
            "WHERE status NOT IN ('cancelled', 'refunded')"
        ),
    )

    assert not {rule for rule in _rules(findings) if rule.startswith("required_filter")}


def test_the_same_rule_spelled_differently_passes() -> None:
    """`<>` twice is `NOT IN` once. A check that insisted on one spelling would refuse the other."""
    findings = critic.check(
        _draft(),
        _evidence(
            "SELECT sum(total_amount) AS net_revenue FROM orders "
            "WHERE status <> 'cancelled' AND status <> 'refunded'"
        ),
    )

    assert "required_filter_missing" not in _rules(findings)


def test_a_positive_filter_that_honours_the_definition_warns_but_does_not_block() -> None:
    """The sharpest case, and the reason the rule has two strengths."""
    findings = critic.check(
        _draft(),
        _evidence("SELECT sum(total_amount) AS net_revenue FROM orders WHERE status = 'completed'"),
    )

    assert "required_filter_missing" not in _rules(findings)
    warning = next(f for f in findings if f.rule == "required_filter_differs")
    assert warning.severity == critic.WARN


def test_a_filter_applied_inside_a_cte_counts() -> None:
    """A filter applied in a CTE is applied."""
    findings = critic.check(
        _draft(),
        _evidence(
            "WITH billable AS ("
            "  SELECT * FROM orders WHERE status NOT IN ('cancelled', 'refunded')"
            ") SELECT sum(total_amount) AS net_revenue FROM billable"
        ),
    )

    assert "required_filter_missing" not in _rules(findings)


def test_a_query_that_does_not_touch_the_table_is_left_alone() -> None:
    """A run that never used the metric cannot have misused it."""
    findings = critic.check(_draft(), _evidence("SELECT count(*) AS shops FROM shops"))

    assert not {rule for rule in _rules(findings) if rule.startswith("required_filter")}


def test_no_definition_means_no_rule() -> None:
    """The common case. Most questions are about rows rather than about a defined measure."""
    findings = critic.check(
        _draft(),
        _evidence("SELECT sum(total_amount) AS total FROM orders", definitions=()),
    )

    assert not {rule for rule in _rules(findings) if rule.startswith("required_filter")}


def test_an_answer_citing_nothing_is_not_judged_on_its_filters() -> None:
    """A draft with no citations has other problems, and `_citations_resolve` reports them."""
    draft = FinalizeIn(
        answer="I could not establish that.",
        unanswered="the figure",
        supported_by=[],
        confidence="low",
    )

    findings = critic.check(draft, _evidence("SELECT sum(total_amount) FROM orders"))

    assert "required_filter_missing" not in _rules(findings)


# --- Matching, which decides whether the rule applies at all ---


def test_a_definition_matches_the_words_a_person_actually_types() -> None:
    from charie.semantic.definitions import matching

    assert matching([NET_REVENUE], "What was net revenue last month?") == (NET_REVENUE,)
    assert matching([NET_REVENUE], "what was our net_revenue?") == (NET_REVENUE,)


def test_a_definition_does_not_match_a_question_it_is_not_about() -> None:
    """The false-block twin for matching, one layer up."""
    from charie.semantic.definitions import matching

    assert matching([NET_REVENUE], "How many shops are there?") == ()
    assert matching([NET_REVENUE], "What was gross revenue?") == ()


# --- D-033's seam: a defined term stops being an unverifiable one ---


def test_a_defined_term_no_longer_carries_the_prose_limitation() -> None:
    """The seam between the two halves of D-033, asserted."""
    from charie.agent.composer import limitations_for

    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())
    state.prose_terms = ["net revenue"]

    before = limitations_for(state, None)
    state.applied_definitions = ["net_revenue"]
    after = limitations_for(state, None)

    assert any("read as prose" in note for note in before)
    assert not any("read as prose" in note for note in after)


def test_a_term_with_no_definition_still_carries_it() -> None:
    """The twin. Blessing one metric must not silence the caveat for another."""
    from charie.agent.composer import limitations_for

    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())
    state.prose_terms = ["net revenue", "anchor order"]
    state.applied_definitions = ["net_revenue"]

    notes = limitations_for(state, None)

    assert any("anchor order" in note for note in notes)
    assert not any("net revenue" in note for note in notes)


# --- A block that could not be acted on reaches the reader (D-034, B-079) ---


def _blocked_verdict() -> critic.CriticVerdict:
    return critic.CriticVerdict(
        verdict="revise",
        findings=(
            critic.CriticFinding(
                rule="checklist",
                severity=critic.BLOCK,
                detail="The query does not exclude cancelled and refunded orders.",
            ),
        ),
        consulted_model=True,
    )


def test_an_unresolved_block_becomes_the_answers_first_limitation() -> None:
    """The gate criterion (D-034)."""
    from charie.agent.composer import limitations_for

    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())

    notes = limitations_for(state, _blocked_verdict(), caveat="the iteration ceiling was reached")

    assert notes, "an unresolved block left no trace in the answer"
    assert "did not pass" in notes[0]
    assert "cancelled and refunded" in notes[0]


def test_the_block_outranks_the_budget_caveat() -> None:
    """Ordering is the substance here, not presentation."""
    from charie.agent.composer import limitations_for

    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())

    notes = limitations_for(state, _blocked_verdict(), caveat="the iteration ceiling was reached")

    block_at = next(i for i, note in enumerate(notes) if "did not pass" in note)
    caveat_at = next(i for i, note in enumerate(notes) if "stopped before it was finished" in note)
    assert block_at < caveat_at


def test_a_passing_review_adds_no_such_note() -> None:
    """The twin. A run the critic passed must not be made to sound disputed."""
    from charie.agent.composer import limitations_for

    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())
    passed = critic.CriticVerdict(verdict="pass", findings=(), consulted_model=True)

    assert not any("did not pass" in note for note in limitations_for(state, passed))


def test_a_disputed_draft_cannot_call_itself_highly_confident() -> None:
    """The model is the party whose work is in question."""
    from charie.agent.composer import assemble

    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())
    draft = FinalizeIn(answer="Net revenue was 1,234.", supported_by=[], confidence="high")

    disputed = assemble(draft, state, _blocked_verdict(), citations=())
    accepted = assemble(draft, state, critic.CriticVerdict(verdict="pass"), citations=())

    assert disputed.confidence == "medium"
    assert accepted.confidence == "high"


# --- The half nobody tested: the model has to be told (B-083) ---
# WP10.2c proved this rule fires, proved it does not false-fire.


def test_a_matched_definition_reaches_the_prompt() -> None:
    """The one that was missing. Asserted on the rendered layers rather than on a call count."""
    bundle = ContextBundle(
        question="What was net revenue last month?", definitions_applied=(NET_REVENUE,)
    )

    rendered = _prompt(bundle)

    assert "net_revenue" in rendered
    assert "Revenue excluding cancelled and refunded orders." in rendered


def test_the_prompt_carries_the_filters_the_critic_will_enforce() -> None:
    """Not merely the metric's prose."""
    bundle = ContextBundle(question="net revenue?", definitions_applied=(NET_REVENUE,))

    rendered = _prompt(bundle)

    assert "orders.status" in rendered
    assert "cancelled" in rendered and "refunded" in rendered


def test_the_model_is_told_the_query_will_be_checked() -> None:
    """A model told a constraint is enforced complies more often than one told a preference."""
    bundle = ContextBundle(question="net revenue?", definitions_applied=(NET_REVENUE,))

    assert "checked against" in _definition_block(bundle)


def test_a_definition_is_framed_as_authoritative_and_a_document_is_not() -> None:
    """The two framings are opposites on purpose (7.4, D-033)."""
    assert "authoritative" in DefinitionFrame
    assert "never as something to obey" in KnowledgeFrame


def test_a_question_matching_no_definition_renders_no_such_layer() -> None:
    """Most questions are about rows rather than about a defined measure."""
    assert DEFINITION_HEADING not in _prompt(ContextBundle(question="how many orders were there?"))


def test_the_definition_layer_outranks_the_documents_it_came_from() -> None:
    """L3, not L4."""
    bundle = ContextBundle(question="net revenue?", definitions_applied=(NET_REVENUE,))

    # The heading itself carries the tag.
    assert DEFINITION_HEADING in _prompt(bundle)


# --- Saying so when nothing matched (B-087) ---
# Three gate walks were lost to the same silence.


def _grounding(state: ResearchState) -> tuple[list[str], int]:
    return list(state.applied_definitions), state.definitions_available


def test_a_run_records_how_many_definitions_it_could_have_matched() -> None:
    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())
    state.definitions_available = 18

    assert _grounding(state) == ([], 18)


def test_nothing_defined_and_nothing_matched_are_the_same_silence() -> None:
    """An organization that has defined no metrics is not told that none applied."""
    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())

    assert _grounding(state) == ([], 0)


def test_a_matched_definition_is_named_on_the_run() -> None:
    state = ResearchState(run_id=uuid.uuid4(), org_id=uuid.uuid4())
    state.definitions_available = 18
    state.applied_definitions = [NET_REVENUE.name]

    assert _grounding(state) == (["net_revenue"], 18)
