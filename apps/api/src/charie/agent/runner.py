"""One question, investigated and answered (architecture M8, Part 4.4)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import select

from charie.agent import composer, critic
from charie.agent.budget import Budget, BudgetState
from charie.agent.capability import (
    CapabilityChasm,
    CapabilityGap,
    JoinGraph,
    encode_inferred_joins,
    load_join_graph,
)
from charie.agent.context import (
    HISTORY_TURNS,
    ContextBundle,
    HistoryTurn,
    build_context,
    chosen,
    history_block,
)
from charie.agent.coverage import (
    Coverage,
    Period,
    asked_for,
    available_period,
    coverage_note,
    describe,
    held_days,
    period_of_values,
)
from charie.agent.critic import CriticVerdict, stated_range
from charie.agent.loop import COMPOSE_PREVIEWS, LoopOutcome, research
from charie.agent.provenance import modes_of
from charie.agent.provenance import reorder as provenance_order
from charie.agent.state import ResearchState, StateFinding
from charie.agent.tools.base import ToolContext
from charie.agent.tools.chart import CreateChartOut
from charie.agent.tools.finalize import FINALIZE, FinalizeIn
from charie.agent.tools.registry import ToolRegistry, default_registry
from charie.catalog.browse import active_catalog
from charie.catalog.cards import offers_measures
from charie.config import Settings
from charie.dal.lease import ConnectionLease
from charie.dal.policy import SourcePolicy
from charie.db.models import QueryExecution, ResultArtifact
from charie.knowledge import embeddings
from charie.llm.base import LLMError
from charie.runs import service as runs
from charie.runs.events import EventWriter
from charie.semantic import definitions as semantic
from charie.semantic import verified as verified_queries
from charie.tenancy.session import org_session

logger = logging.getLogger(__name__)

__all__ = ["RunOutcome", "execute_run", "relevant_pairs"]

#: Stopping for one of these is `budget_exhausted`.
_BUDGET_DIMENSIONS = frozenset({"iterations", "queries", "llm_calls", "tokens", "wall_seconds"})

#: How many times a draft may be criticised.
MAX_CRITIC_PASSES = 2

#: The critic's verdict is three short reasons at most, so its output ceiling can be small.
CRITIC_OUTPUT_TOKENS = 800

#: The composed answer is the longest structured reply a run asks for: the prose.
COMPOSE_OUTPUT_TOKENS = 4096


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """What happened, for a caller that wants to know without re-reading the run."""

    run_id: uuid.UUID
    status: str
    #: `answered` | `partly` | `refused` (D-044).
    state: str
    #: What the run could not answer. Non-empty exactly when `state` is `partly`.
    unanswered: str
    answer: str
    execution_ids: tuple[str, ...] = ()
    llm_calls: int = 0
    #: How many research steps it took. 0 for a run that never got past context.
    iterations: int = 0
    #: The ceiling or rule that stopped the search, when one did.
    stopped_by: str | None = None
    #: What the answer does not establish (WP9.2).
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Working:
    """Everything one run carries while it is running."""

    state: ResearchState
    budget: BudgetState


async def execute_run(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    data_source_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    role: str = "reader",
    registry: ToolRegistry | None = None,
    settings: Settings | None = None,
    budget: Budget | None = None,
    as_of: date | None = None,
) -> RunOutcome:
    """Drive one queued run to an ending."""
    tools = registry if registry is not None else _registry_with_finalize()
    events = EventWriter(org_id=org_id, run_id=run_id)
    working = _Working(
        state=ResearchState(run_id=run_id, org_id=org_id),
        budget=BudgetState(budget=budget if budget is not None else Budget()),
    )
    # One connection for the whole run (B-176).
    lease = ConnectionLease(org_id, data_source_id)
    context = ToolContext(
        org_id=org_id,
        run_id=run_id,
        role=role,
        actor_user_id=actor_user_id,
        data_source_id=data_source_id,
        as_of=as_of,
        lease=lease,
        # Resolved once for the run rather than per tool call.
        embedder=embeddings.get_embedder(settings),
        settings=settings,
    )

    await runs.transition(org_id=org_id, run_id=run_id, status="running")
    ending, outcome = "failed", None
    try:
        outcome = await _investigate(
            context=context, tools=tools, events=events, working=working, settings=settings
        )
        # A run stopped by a ceiling is an answer with caveats, not a failure.
        ending = (
            "budget_exhausted" if working.state.stopped_by in _BUDGET_DIMENSIONS else "completed"
        )
        return outcome
    except LLMError as error:
        # The provider, not the question.
        await _record_failure(events, working, str(error), category="llm_error", run_id=run_id)
        return _failed(run_id, working)
    except Exception as error:
        await _record_failure(events, working, str(error), category="internal_error", run_id=run_id)
        return _failed(run_id, working)
    finally:
        # Closed before the run is finished, and in `finally` (B-176).
        await lease.aclose()
        # In `finally`, because a run that never ends is the one failure with no symptom until...
        await _finish(org_id=org_id, run_id=run_id, status=ending, working=working, outcome=outcome)


#: How many capability facts the planner is told up front.
CAPABILITY_NOTE_LIMIT = 20


def relevant_pairs[PairT: CapabilityGap | CapabilityChasm](
    pairs: Sequence[PairT], selected: Sequence[str]
) -> tuple[PairT, ...]:
    """The pairs this question is about, not the ones that sort first (B-056)."""
    wanted = {name.strip().strip('"').split(".")[-1].lower() for name in selected}
    if not wanted:
        return tuple(pairs[:CAPABILITY_NOTE_LIMIT])

    def rank(pair: PairT) -> int:
        return -((pair.left in wanted) + (pair.right in wanted))

    touching = [pair for pair in pairs if pair.left in wanted or pair.right in wanted]
    return tuple(sorted(touching, key=rank)[:CAPABILITY_NOTE_LIMIT])


def source_of(context: ToolContext) -> uuid.UUID:
    """The run's data source. `ToolContext` allows none because a tool may run without one."""
    if context.data_source_id is None:  # pragma: no cover - execute_run requires it
        raise ValueError("a run cannot be executed without a data source")
    return context.data_source_id


async def _investigate(
    *,
    context: ToolContext,
    tools: ToolRegistry,
    events: EventWriter,
    working: _Working,
    settings: Settings | None,
) -> RunOutcome:
    """Context, then the bounded loop, then an answer — whatever the loop found."""
    state, budget = working.state, working.budget
    state.question = await _question_of(context.org_id, context.run_id)
    history = await _history_of(context.org_id, context.run_id)

    bundle = await build_context(
        org_id=context.org_id,
        question=state.question,
        data_source_id=context.data_source_id,
        as_of=context.as_of,
        history=history,
        # The run's own embedder, so card search is hybrid and its query embedding is charged to...
        embedder=context.embedder,
        run_id=context.run_id,
        actor_user_id=context.actor_user_id,
        settings=settings,
    )
    # What this organization means by the words in the question (D-033, WP10.2c).
    available = await semantic.definitions_for(context.org_id, source_of(context))
    applied = semantic.matching(available, state.question)
    # Both numbers, always (B-087).
    state.definitions_available = len(available)
    if applied:
        bundle = replace(bundle, definitions_applied=applied)
        state.applied_definitions = [definition.name for definition in applied]
        # What the definition makes the answer say (revision 0033).
        state.definition_caveats = {
            definition.name: definition.caveat for definition in applied if definition.caveat
        }

    # How this organization has answered questions like this one (arch 5.4).
    examples = verified_queries.matching(
        await verified_queries.verified_for(context.org_id, source_of(context)), state.question
    )
    if examples:
        bundle = replace(bundle, verified_applied=examples)

    state.phase = "context"
    state.table_names = list(bundle.table_names)
    # Which of the retrieved tables could have answered this — the ones with something to add up.
    state.candidate_sources = [
        card.qualified for card in bundle.cards if offers_measures(card.card_text)
    ]
    state.as_of = bundle.as_of.isoformat()
    await _checkpoint(context, working)
    # The join graph, loaded once. The pairs that cannot be joined are told to the planner as fact.
    from charie.dal.policy import source_policy

    source_id = source_of(context)

    graph = await load_join_graph(context.org_id, source_id)
    policy = await source_policy(context.org_id, source_id)
    gaps = relevant_pairs(graph.unreachable_pairs(), bundle.table_names)
    chasms = relevant_pairs(graph.comparable_pairs(), bundle.table_names)

    # What periods this database can speak about (B-157, D-058).
    offered = set(bundle.table_names)
    catalog = await active_catalog(context.org_id, source_id)
    dated = [
        (column.data_type, column.min_val, column.max_val)
        for table in catalog.tables
        if f"{table.schema_name}.{table.table_name}" in offered
        for column in table.columns
    ]
    available = available_period(dated)
    # The period this question asked for, against the period the data holds (D-051).
    wanted = stated_range(state.question, bundle.as_of)
    asked = asked_for(
        None if wanted is None else (wanted.start.isoformat(), wanted.end.isoformat()),
        held_days(dated),
    )
    state.coverage = {
        "verdict": asked.verdict,
        "asked": list(asked.asked) if asked.asked else None,
        "held": list(asked.held) if asked.held else None,
        "overlap": list(asked.overlap) if asked.overlap else None,
    }
    # Which rows are observed and which are modelled (D-053, D-058, B-157).
    provenance = {
        f"{table.schema_name}.{table.table_name}": modes_of(
            [(column.name, column.top_values) for column in table.columns]
        )
        for table in catalog.tables
        if f"{table.schema_name}.{table.table_name}" in offered
    }
    # Observed data first, among the cards that could each answer.
    bundle = replace(
        bundle,
        cards=provenance_order(
            bundle.cards,
            modes=lambda card: provenance.get(card.qualified, ()),
            answers_questions=lambda card: offers_measures(card.card_text),
        ),
    )

    layout = chosen(bundle)
    await events.emit(
        "context_selected",
        {
            "tables": list(bundle.table_names),
            # What the prompt will carry, not what the search returned (B-160).
            "tables_in_full": layout.in_full,
            "tables_in_outline": layout.in_outline,
            "tables_dropped": len(bundle.cards) - len(layout.cards),
            "restrictions": len(bundle.restrictions),
            # How much of the thread this run was given.
            "history_turns": len(bundle.history),
            # Which definitions governed this run, and how many there were to match (B-087).
            "definitions_applied": list(state.applied_definitions),
            "definitions_available": state.definitions_available,
            "tables_found_via": "thread" if bundle.cards_from_thread else "question",
            # Which arm of the card search reached each table (B-018).
            "tables_found_by": {card.qualified: card.found_by for card in bundle.cards},
            # In the trace because a person reading an answer about "last month" is owed the...
            "as_of": bundle.as_of.isoformat(),
        },
    )

    state.capability = {
        # What each offered table's rows are.
        "provenance": {table: list(modes) for table, modes in provenance.items() if modes},
        # Which of the joins on offer rest on a measurement rather than on a declared key (D-050).
        "inferred": encode_inferred_joins(graph.inferred_joins(bundle.table_names)),
        "unreachable": [{"left": gap.left, "right": gap.right} for gap in gaps],
        "comparable": [
            {"left": chasm.left, "right": chasm.right, "via": chasm.via} for chasm in chasms
        ],
        # Carried on the state so the composer can compare an answer against it without a second...
        "available_period": None if available is None else [available.earliest, available.latest],
    }
    await events.emit(
        "capability_checked",
        {
            "unreachable": [f"{gap.left} ↔ {gap.right}" for gap in gaps],
            "comparable": [f"{chasm.left} ↔ {chasm.right} via {chasm.via}" for chasm in chasms],
            # Emitted even when it is null, which is the whole point.
            "available_period": None if available is None else str(available),
        },
    )
    notes: list[str] = []
    if gaps:
        # What is known, not what is forbidden.
        notes.append(
            "The catalog records no link between these tables — no declared foreign "
            "key joins them: "
            + "; ".join(f"{gap.left} and {gap.right}" for gap in gaps)
            + ". That is the limit of what is known here, not a prohibition. A join "
            "that cannot be verified returns every row of one against every row of "
            "the other rather than an error, so do not write one; if the question "
            "needs it, set answerable to false and say which link is missing."
        )
    if chasms:
        # Deliberately phrased as an instruction rather than a prohibition (D-026).
        notes.append(
            "These tables are related only through a shared parent, so joining them "
            "directly multiplies their rows together instead of matching them: "
            + "; ".join(
                f"{chasm.left} and {chasm.right} (both under {chasm.via})" for chasm in chasms
            )
            + ". To combine such a pair, aggregate each side to the shared key in its "
            "own subquery or CTE first, then join the two aggregates. Do not join the "
            "detail rows."
        )
    # Last of the notes, because it is the only one that is not about a join.
    if period_note := coverage_note(available, asked):
        notes.append(period_note)
    if notes:
        bundle = bundle.with_capability_note(" ".join(notes))

    async def save() -> None:
        await _checkpoint(context, working)

    async def keep(finding: StateFinding) -> None:
        # Written when it is reached, so an interrupted run keeps what it had concluded and the...
        await runs.add_finding(
            org_id=context.org_id,
            run_id=context.run_id,
            statement=finding.statement,
            support=finding.support,
            confidence=finding.confidence
            if finding.confidence in {"high", "medium", "low"}
            else "medium",
        )

    outcome = await research(
        context=context,
        tools=tools,
        events=events,
        state=state,
        budget=budget,
        bundle=bundle,
        graph=graph,
        dialect=policy.dialect,
        checkpoint=save,
        record_finding=keep,
        settings=settings,
    )

    if outcome.ending == "refused" and not state.executions:
        # Nothing was ever run, so there is nothing to compose from and nothing to cite.
        return await _finalize_refusal(context, events, working, outcome.refusal)

    if state.every_query_failed():
        # B-095, and the owner's decision (D-038).
        return await _finalize_refusal(
            context, events, working, _failed_refusal(state, outcome), caveat=outcome.caveat
        )

    # Compose, criticise, and — at most once — go round again (arch M9).
    draft = await _compose(context, events, working, outcome, bundle, settings)
    verdict = await _validate(context, events, working, outcome, draft, bundle, settings)

    if verdict.blocked and _may_re_enter(working):
        outcome, draft, verdict = await _second_pass(
            context=context,
            tools=tools,
            events=events,
            working=working,
            bundle=bundle,
            graph=graph,
            dialect=policy.dialect,
            save=save,
            keep=keep,
            verdict=verdict,
            previous=outcome,
            settings=settings,
        )

    state.critic = verdict.as_payload()
    cited = await _verified_citations(draft.supported_by, working, events)
    return await _write_ending(
        context,
        events,
        working,
        draft,
        cited,
        verdict=verdict,
        caveat=outcome.caveat,
        tools=tools,
    )


def _may_re_enter(working: _Working) -> bool:
    """Whether the run has both permission and budget for one more pass."""
    if working.state.critic_passes >= MAX_CRITIC_PASSES:
        return False
    return working.budget.exhausted() is None


async def _validate(
    context: ToolContext,
    events: EventWriter,
    working: _Working,
    outcome: LoopOutcome,
    draft: FinalizeIn,
    bundle: ContextBundle,
    settings: Settings | None,
) -> CriticVerdict:
    """Both critic stages, and the verdict in the trace."""
    from charie.llm import service as llm
    from charie.llm.base import CallLimits, Message

    state, budget = working.state, working.budget
    state.critic_passes += 1

    evidence = critic.Evidence(
        question=state.question,
        # The thread, for the model half only (D-029).
        history=bundle.history,
        as_of=date.fromisoformat(state.as_of) if state.as_of else datetime.now(UTC).date(),
        state=state,
        statements=await critic.statements_for(context.org_id, state.execution_ids()),
        previews=outcome.previews,
        dialect=(await source_policy_for(context)).dialect,
        # The definitions this question matched.
        definitions=bundle.definitions_applied,
        # What the data holds, so the range rule judges against the period that exists rather...
        held=_held_window(state),
    )
    deterministic = critic.check(draft, evidence)

    model: critic.CriticOut | None = None
    blocked_already = any(finding.severity == critic.BLOCK for finding in deterministic)
    if not blocked_already and budget.exhausted() is None:
        completion = await llm.complete(
            role="critic",
            org_id=context.org_id,
            messages=[Message(role="user", content=critic.rubric(draft, evidence, deterministic))],
            schema=critic.CriticOut,
            run_id=context.run_id,
            actor_user_id=context.actor_user_id,
            settings=settings,
            # Small on purpose (B-052): the schema is three short reasons.
            limits=CallLimits(max_output_tokens=CRITIC_OUTPUT_TOKENS),
        )
        budget.spend_llm(completion.usage.total_tokens)
        model = completion.parsed_as(critic.CriticOut)

    verdict = critic.combine(deterministic, model)
    await events.emit("critic_verdict", verdict.as_payload())
    return verdict


async def _second_pass(
    *,
    context: ToolContext,
    tools: ToolRegistry,
    events: EventWriter,
    working: _Working,
    bundle: ContextBundle,
    graph: JoinGraph,
    dialect: str,
    save: Callable[[], Awaitable[None]],
    keep: Callable[[StateFinding], Awaitable[None]],
    verdict: CriticVerdict,
    previous: LoopOutcome,
    settings: Settings | None,
) -> tuple[LoopOutcome, FinalizeIn, CriticVerdict]:
    """The one bounded re-entry (arch M9), and its second verdict."""
    state = working.state
    await runs.transition(org_id=context.org_id, run_id=context.run_id, status="validating")
    await runs.transition(org_id=context.org_id, run_id=context.run_id, status="running")

    # The critic's reasons become open questions.
    state.open_questions.extend(finding.detail for finding in verdict.blocking)
    state.phase = "planning"
    await save()

    outcome = await research(
        context=context,
        tools=tools,
        events=events,
        state=state,
        budget=working.budget,
        bundle=bundle,
        graph=graph,
        dialect=dialect,
        checkpoint=save,
        record_finding=keep,
        settings=settings,
    )
    # Re-entry adds evidence; it must not erase the first pass's results (B-189).
    previews = dict((*previous.previews, *outcome.previews))
    outcome = replace(outcome, previews=tuple(previews.items())[-COMPOSE_PREVIEWS:])
    draft = await _compose(
        context, events, working, outcome, bundle, settings, correction=verdict.reasons()
    )
    second = await _validate(context, events, working, outcome, draft, bundle, settings)
    return outcome, draft, second


async def source_policy_for(context: ToolContext) -> SourcePolicy:
    """The policy for this run's source, for whoever needs its dialect."""
    from charie.dal.policy import source_policy

    if context.data_source_id is None:  # pragma: no cover - execute_run requires one
        raise ValueError("a run cannot be validated without a data source")
    return await source_policy(context.org_id, context.data_source_id)


async def _compose(
    context: ToolContext,
    events: EventWriter,
    working: _Working,
    outcome: LoopOutcome,
    bundle: ContextBundle,
    settings: Settings | None,
    correction: str = "",
) -> FinalizeIn:
    """One call that turns what the loop found into an answer that cites it."""
    from charie.llm import service as llm
    from charie.llm.base import CallLimits, Message

    state, budget = working.state, working.budget
    evidence = (
        "\n".join(
            f"- {reference.execution_id}: {reference.summary}" for reference in state.executions
        )
        or "- (no query returned a result)"
    )
    concluded = "\n".join(f"- {finding.statement}" for finding in state.findings) or "- (none)"
    # The actual rows of the most recent queries.
    results = "\n\n".join(
        f"Result of {execution_id}:\n{rendered}" for execution_id, rendered in outcome.previews
    )

    revise = ""
    if correction:
        # The second attempt. The critic's reasons are the instruction.
        revise = (
            "\n\nA reviewer rejected your previous answer for these reasons:\n"
            f"{correction}\n"
            "Address each one. Where the evidence does not let you, say so in the "
            "answer as a stated limitation rather than leaving it out."
        )

    caveat = ""
    if outcome.caveat:
        caveat = (
            f"\n\nIMPORTANT: the investigation stopped early. {outcome.caveat} "
            "Say plainly in your answer that this is a partial result and why, "
            "and answer with what the evidence below does support."
        )

    # The thread, framed (D-029). This is the call that writes the words a person reads.
    thread = history_block(bundle.history)
    prompt = (
        (f"{thread}\n\n" if thread else "") + f"The question was: {state.question}\n\n"
        f"Queries run, with what each returned:\n{evidence}\n\n"
        f"What you concluded along the way:\n{concluded}\n\n"
        f"{results}{caveat}{revise}\n\n"
        "Answer the question in plain words for the person who asked. Use only "
        "these numbers. Cite in supported_by the execution ids your answer rests "
        "on. If the evidence does not actually answer the question, name the missing "
        "part in unanswered and explain it in the answer. If no part can be answered, "
        "set unanswered to 'this question' and leave supported_by empty. A query "
        "finding no records for a period does not establish zero business activity: "
        "say there is no data for that period rather than report zero sales or profit. "
        "Cite executions for the substantive results you can report, not empty "
        "executions as if they answered the business question.\n\n"
        # B-109, second lever.
        "Write about the data and never about the chart. Whether a picture can "
        "be drawn is decided after you answer and shown in its own place, so a "
        "sentence about what a chart can or cannot do belongs nowhere in this "
        "answer — to the reader it reads as the product being broken."
        + READABLE_ANSWER_RULE
        + PARTIAL_RESULT_RULE
    )
    from charie.agent.reviews import (
        BRIEF_DISPLAY,
        REVIEW_DISPLAY,
        VISUAL_DISPLAY,
        brief_requested,
        review_requested,
    )

    if brief_requested(state.question):
        prompt += f"\n\n{BRIEF_DISPLAY}"
    else:
        prompt += f"\n\n{VISUAL_DISPLAY}"
        if review_requested(state.question):
            prompt += f"\n\n{REVIEW_DISPLAY}"
    completion = await llm.complete(
        role="compose",
        org_id=context.org_id,
        messages=[Message(role="user", content=prompt)],
        schema=FinalizeIn,
        run_id=context.run_id,
        actor_user_id=context.actor_user_id,
        settings=settings,
        limits=CallLimits(max_output_tokens=COMPOSE_OUTPUT_TOKENS),
    )
    budget.spend_llm(completion.usage.total_tokens)
    return completion.parsed_as(FinalizeIn)


def _failed_refusal(state: ResearchState, outcome: LoopOutcome) -> str:
    """What to tell the reader when no query in the run came back (B-095)."""
    if outcome.refusal:
        return outcome.refusal
    if detail := composer.failure_detail(state):
        return (
            "I could not answer that from this data. No query in this run "
            f"reached the database: {detail}"
        )
    # Every attempt was refused before it was sent and none was ever corrected.
    return "I could not answer that from this data. No query in this run returned a result."


async def _finalize_refusal(
    context: ToolContext,
    events: EventWriter,
    working: _Working,
    reason: str,
    *,
    caveat: str = "",
) -> RunOutcome:
    """End without a further model call."""
    # The whole question is what is unanswered here.
    final = FinalizeIn(
        answer=reason, unanswered="this question", supported_by=[], confidence="high"
    )
    return await _write_ending(context, events, working, final, (), caveat=caveat)


#: What to say when a result arrived in part (B-113, B-111).
READABLE_ANSWER_RULE = (
    "\n\nWrite the answer as Markdown, for a busy person who is not a data "
    "analyst.\n"
    "- Use short `##` headings when the answer has more than one part.\n"
    "- Put every list of things on its own bullet or numbered line. Never run a "
    "ranked list through a sentence with commas.\n"
    "- Use a table when each item carries two or more numbers.\n"
    "- **Bold** the names and the money. Bold sparingly; if half the answer is "
    "bold, none of it is.\n"
    "- Lead with the answer. Put what is missing or uncertain at the end, under "
    "its own heading.\n\n"
    "Use everyday words and short sentences. Prefer 'waste' to 'avoidable-waste "
    "exposure', 'we could not see all the rows' to 'prompt/tool display limits', "
    "'left over' to 'deduplicated'. If a plain word will do, use it. A reader "
    "should not need a second reading to learn what to do next.\n"
    "Being simple is not being vague: keep every number, every name and every "
    "limit exactly as the evidence gives them.\n\n"
    "Sound like a helpful colleague talking to the owner. Use short, natural "
    "sentences and familiar words: 'people spent less per order' rather than "
    "'weighted average order value declined'; 'restaurants open in both months' "
    "rather than 'comparable outlet population'; 'we do not know why yet' rather "
    "than 'the evidence does not establish causality'. Explain what a change "
    "means before describing the method. Keep definitions and caveats accurate "
    "but brief; do not turn the answer into an audit report.\n"
    "Highlight only the few changes that matter. Keep direction and figure "
    "together, for example **up 6.2%** or **Outlet A, down 18.2%**, so the screen "
    "can highlight the complete phrase. Do not bold a percentage on its own "
    "while leaving 'up' or 'down' outside it. Use ==a key point== sparingly for "
    "neutral emphasis. Keep plain totals bold, not every sentence highlighted.\n\n"
    # B-179. The owner met `310817.08999999997` in a table of monthly sales.
    "Write money in the requested or evidenced currency, for example **USD 310,817**, "
    "with thousands separated and rounded to whole units unless the figure is "
    "under 100. Do not guess a currency or convert amounts without evidence. "
    "Keep average spend per order and unit prices to two decimal places. Write weights "
    "as **1,973 kg**. Never print more decimal places than the number deserves; "
    "a total to eleven decimals is noise wearing the clothes of precision. Do "
    "not invent precision the evidence does not have either — if a figure is "
    "modelled, round it and say so rather than quoting it to the cent.\n\n"
    # B-180. The same answer ranked "Improve Outlet D sales — RM 20,469" as an action.
    "When the question asks what to do — actions, priorities, a focus list — "
    "every row must be something a person could start this week, not a number "
    "with a verb attached. 'Improve Outlet D sales' is a restatement of the "
    "figure beside it. 'Outlet D sells RM 20,469 a month against Outlet A's "
    "RM 62,000 on the same menu; its three worst-selling dishes are X, Y and Z, "
    "so start by checking whether they are being offered at all' is an action. "
    "Say **which** dish, **which** outlet, **which** day or shift, and what the "
    "evidence suggests is behind it. Where the data cannot tell you the cause, "
    "say what to look at rather than inventing one — 'check the prep schedule "
    "for Tuesday' is honest, 'staff are over-prepping' is a guess wearing a "
    "recommendation's clothes.\n"
    "Rank by the money at stake and say what that money is: the sales it "
    "protects, or the waste it removes. An action whose size nobody can see is "
    "one nobody can schedule against the rest of their week."
)


PARTIAL_RESULT_RULE = (
    "\n\nA result marked `truncated` reached you in part: `row_count` is how many "
    "rows the query returned, and the rows you were given are the ones that fit "
    "in this prompt. That is a limit of ours and not of the data. Answer with "
    "everything the rows you have do establish. Do not describe a partial result "
    "as though it held nothing: you have those rows and the reader is entitled to "
    "what they show. Do not refuse a question the data answered merely because "
    "you were shown part of the answer.\n"
    # B-173. This used to end "name both numbers", and the model did — in the prose.
    "Do not explain the truncation itself in your answer. The platform states "
    "which query was cut short, and by how much, in its own limitations section. "
    "A paragraph about row counts inside an answer about the question is our "
    "plumbing showing through."
    # B-174. The same product appeared twice at two prices in one answer.
    "\n\nIf the same thing carries different numbers in different results, do not "
    "print both as though they were the same measure. Say what makes them "
    "different — the filter, the period, the table — or use one and say which. A "
    "reader who sees one name with two numbers and no explanation stops trusting "
    "both."
)


async def _coverage_for(
    context: ToolContext, state: ResearchState, cited: Sequence[str]
) -> Coverage:
    """What period the answer's own results covered, against what the catalog records."""
    available: object = state.capability.get("available_period")
    ends: list[str] = (
        [str(end) for end in cast(list[object], available)] if isinstance(available, list) else []
    )
    period = Period(earliest=ends[0], latest=ends[1]) if len(ends) == 2 else None
    if not cited:
        return describe(answered=None, available=period, reason="the answer cites no result")

    values: list[object] = []
    reason = ""
    async with org_session(context.org_id) as session:
        rows = (
            await session.execute(
                select(ResultArtifact, QueryExecution)
                .join(QueryExecution, QueryExecution.id == ResultArtifact.query_execution_id)
                .where(QueryExecution.run_id == context.run_id)
            )
        ).all()
    for artifact, execution in rows:
        if str(execution.id) not in set(cited):
            continue
        sample = list(artifact.sample_rows or [])
        if artifact.truncated:
            reason = reason or (
                "a result the answer rests on was cut off at the row limit, so its "
                "last period is not its latest"
            )
            continue
        if execution.row_count is not None and execution.row_count != len(sample):
            reason = reason or (
                f"a result the answer rests on kept {len(sample)} of its "
                f"{execution.row_count} rows, so its earliest and latest are not known"
            )
            continue
        values.extend(cell for row in sample for cell in row)

    answered, why = period_of_values(values, truncated=False)
    return describe(
        answered=answered, available=period, reason=reason or (why if not values else "")
    )


def _held_window(state: ResearchState) -> tuple[str, str] | None:
    """The inclusive window the data holds, off the state the capability step wrote."""
    held: object = state.coverage.get("held")
    if not isinstance(held, list):
        return None
    ends = [str(end) for end in cast(list[object], held)]
    return (ends[0], ends[1]) if len(ends) == 2 else None


async def _write_ending(
    context: ToolContext,
    events: EventWriter,
    working: _Working,
    final: FinalizeIn,
    cited: tuple[str, ...],
    verdict: CriticVerdict | None = None,
    caveat: str = "",
    tools: ToolRegistry | None = None,
) -> RunOutcome:
    """Record the answer, what backs it, what it does not establish, and the trace."""
    state = working.state
    # Before `assemble`, because the composer owns the order limitations are read in and a...
    coverage = await _coverage_for(context, state, cited)
    state.capability["coverage"] = coverage.as_payload()
    composed = composer.assemble(final, state, verdict, citations=cited, caveat=caveat)
    chart = await _chart_for(context, tools, events, final, cited)
    await runs.record_answer(
        org_id=context.org_id,
        run_id=context.run_id,
        content=final.answer,
        limitations=list(composed.limitations),
        # In the trace whatever it says, including when it says it could not look.
        coverage=coverage.as_payload(),
        # B-100. `assemble` has built this since Phase 9 and this call dropped it.
        method=composed.method,
        chart=chart,
    )

    # The loop already persisted each finding as it reached it.
    already = {finding.statement.strip() for finding in state.findings}
    evidence = {tuple(sorted(finding.support)) for finding in state.findings}
    restated = final.answer.strip() in already or tuple(sorted(cited)) in evidence
    if cited and not restated:
        # A finding only when there is something to stand behind.
        await runs.add_finding(
            org_id=context.org_id,
            run_id=context.run_id,
            statement=final.answer,
            support=cited,
            confidence=final.confidence
            if final.confidence in {"high", "medium", "low"}
            else "medium",
        )

    # Mark the findings this answer rests on.
    await runs.mark_cited(org_id=context.org_id, run_id=context.run_id, executions=cited)

    state.phase = "finished"
    await _checkpoint(context, working)
    return RunOutcome(
        run_id=context.run_id,
        status="completed",
        state=composed.state,
        unanswered=composed.unanswered,
        answer=final.answer,
        execution_ids=cited,
        llm_calls=working.budget.llm_calls,
        iterations=state.iteration,
        stopped_by=state.stopped_by,
        limitations=composed.limitations,
    )


async def _chart_for(
    context: ToolContext,
    tools: ToolRegistry | None,
    events: EventWriter,
    final: FinalizeIn,
    cited: tuple[str, ...],
) -> dict[str, object] | None:
    """The chart the answer asked for, drawn or refused (WP11.1)."""
    ask = final.chart
    if not ask.of.strip() or tools is None:
        # `tools is None` is the refusal path.
        return None

    if ask.of not in cited:
        # Not a refusal about the data: the model pointed at a result this answer does not rest on.
        return {
            "declined": (
                "No chart was drawn: the answer asked to chart a result it does not cite."
            ),
            "code": "uncited_execution",
        }

    result = await tools.call(
        context,
        "create_chart_spec",
        {
            "execution_id": ask.of,
            "mark": ask.mark,
            "x": ask.x,
            "y": ask.y,
            # B-109. Empty means "no split", which is the common case.
            "series": ask.series.strip() or None,
        },
        events=events,
    )
    if not result.ok or not isinstance(result.data, CreateChartOut):
        return {
            "declined": ("No chart was drawn: the chart could not be built from that result."),
            "code": result.code or "chart_failed",
        }

    out = result.data
    if out.spec is not None:
        return {"spec": out.spec}
    return {"declined": out.declined, "code": out.code}


async def _verified_citations(
    claimed: list[str], working: _Working, events: EventWriter
) -> tuple[str, ...]:
    """Only ids this run really produced."""
    produced = working.state.execution_ids()
    real = [item for item in claimed if item in produced]
    if len(real) != len(claimed):
        await events.emit(
            "error",
            {
                "category": "unverifiable_citation",
                "safe_message": (
                    f"{len(claimed) - len(real)} cited execution id(s) were not produced "
                    "by this run and were dropped"
                ),
            },
        )
    return tuple(real)


async def _question_of(org_id: uuid.UUID, run_id: uuid.UUID) -> str:
    view = await runs.get_run(org_id=org_id, run_id=run_id)
    return view.question


async def _history_of(org_id: uuid.UUID, run_id: uuid.UUID) -> tuple[HistoryTurn, ...]:
    """The thread this question follows (D-029, B-064)."""
    prior = await runs.conversation_history(org_id=org_id, run_id=run_id, turns=HISTORY_TURNS)
    return tuple(HistoryTurn(question=turn.question, answer=turn.answer) for turn in prior)


async def _checkpoint(context: ToolContext, working: _Working) -> None:
    """Persist the working state at a step boundary (architecture 0.2.4)."""
    from sqlalchemy import update

    from charie.db.models import AgentRun

    async with org_session(context.org_id) as session:
        await session.execute(
            update(AgentRun)
            .where(AgentRun.id == context.run_id)
            .values(state=working.state.as_json(), budget=working.budget.as_json())
        )


async def _record_failure(
    events: EventWriter,
    working: _Working,
    message: str,
    *,
    category: str,
    run_id: uuid.UUID,
) -> None:
    """End the run, and say why somewhere an operator can read it (B-126)."""
    logger.exception("run %s failed (%s): %s", run_id, category, message)
    working.state.phase = "finished"
    await events.emit("error", {"category": category, "safe_message": message[:500]})


def _failed(run_id: uuid.UUID, working: _Working) -> RunOutcome:
    return RunOutcome(
        run_id=run_id,
        status="failed",
        state="refused",
        unanswered="",
        answer="",
        execution_ids=working.state.execution_ids(),
        llm_calls=working.budget.llm_calls,
        iterations=working.state.iteration,
        stopped_by=working.state.stopped_by,
    )


async def _finish(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    status: str,
    working: _Working,
    outcome: RunOutcome | None,
) -> None:
    """Move the run to its ending, once, whatever happened above."""
    await runs.transition(
        org_id=org_id,
        run_id=run_id,
        status=status,
        failure_reason=("The run could not be completed." if status == "failed" else None),
        # The ending's other half (B-133).
        state=outcome.state if outcome is not None else "refused",
        unanswered=outcome.unanswered if outcome is not None else "",
        totals={
            "llm_calls": working.budget.llm_calls,
            "queries": working.budget.queries,
            "iterations": working.state.iteration,
            "tokens": working.budget.tokens,
            "stopped_by": working.state.stopped_by,
            "state": outcome.state if outcome is not None else "refused",
        },
    )


def _registry_with_finalize() -> ToolRegistry:
    """The default tool set plus ``finalize``."""
    registry = default_registry()
    registry.register(FINALIZE)
    return registry
