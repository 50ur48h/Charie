"""The bounded research loop (architecture 4.4, diagram 5)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from charie.agent.budget import BudgetState
from charie.agent.capability import JoinGraph
from charie.agent.context import ContextBundle, Definition, history_block
from charie.agent.planner import Plan, plan_query
from charie.agent.state import (
    ExecutionRef,
    ResearchState,
    StateFinding,
    Step,
    merge_by_evidence,
)
from charie.agent.tools.base import ToolContext, ToolResult
from charie.agent.tools.knowledge import PassageOut, SearchKnowledgeOut
from charie.agent.tools.registry import ToolRegistry
from charie.agent.tools.sql import RunSqlOut
from charie.config import Settings
from charie.dal.validator import tables_named
from charie.llm import service as llm
from charie.llm.base import Message
from charie.runs.events import EventWriter

__all__ = ["LoopOutcome", "Reflection", "research"]

#: Two consecutive barren iterations end the loop (4.4).
BARREN_LIMIT = 2

#: How many recent results the composer is shown in full.
COMPOSE_PREVIEWS = 3

#: A result small enough that its values are the finding — the aggregate case.
INLINE_CELLS = 3

#: How many terms one run may look up in its documents (B-075, D-032).
MAX_LOOKUPS = 2

#: How many passages a lookup puts in front of the next plan.
LOOKUP_PASSAGES = 3


class ReflectFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=500)
    supported_by: list[str] = Field(default_factory=list[str], max_length=10)
    confidence: str = Field(default="medium")


class Reflection(BaseModel):
    """What the model concluded from the last result, and whether to go on.

    Closed and fully required, like every other structured call in this codebase,
    so a provider that can constrain decoding enforces the shape rather than
    suggesting it (B-033).

    ``rationale`` is written into the trace, so it is explicitly a **short public
    string** — 10.3's payloads are built for eyes and never carry raw model
    reasoning.
    """

    model_config = ConfigDict(extra="forbid")

    findings: list[ReflectFinding] = Field(default_factory=list[ReflectFinding], max_length=10)
    open_questions: list[str] = Field(default_factory=list[str], max_length=10)
    next_purpose: str = Field(default="", max_length=300)
    done: bool = Field(description="True when the question is answered or cannot be taken further.")
    rationale: str = Field(default="", max_length=300)


@dataclass(frozen=True, slots=True)
class LoopOutcome:
    """Why the loop stopped, for the caller that has to compose an answer."""

    #: answered | refused | exhausted | no_progress
    ending: str
    #: Set when a ceiling stopped it, so the answer can say which.
    caveat: str = ""
    #: The planner's own words when it judged the question unanswerable.
    refusal: str = ""
    #: Successful executions, newest last — what a citation may name.
    execution_ids: tuple[str, ...] = ()
    #: `(execution_id, rendered result)` for the most recent successful queries.
    previews: tuple[tuple[str, str], ...] = ()


@dataclass
class _Progress:
    """Whether the last iteration was worth its budget."""

    findings_added: int = 0
    questions_opened: int = 0
    notes: list[str] = field(default_factory=list[str])

    @property
    def moved(self) -> bool:
        return self.findings_added > 0 or self.questions_opened > 0


_WHITESPACE = re.compile(r"\s+")


def proposed_hash(sql: str) -> str:
    """A hash of what the model proposed, normalised for whitespace and case."""
    collapsed = _WHITESPACE.sub(" ", sql.strip().lower())
    return hashlib.sha256(collapsed.encode()).hexdigest()[:16]


def summarize(result: RunSqlOut, purpose: str) -> str:
    """One line describing what came back — architecture 4.4's Observe, in code."""
    shape = f"{result.row_count} row{'' if result.row_count == 1 else 's'}"
    if result.masked_columns:
        shape += f", {len(result.masked_columns)} column(s) masked by policy"
    if result.row_count == 0:
        return f"{purpose}: no rows matched."
    first = result.rows[0] if result.rows else []
    if result.row_count == 1 and len(first) <= INLINE_CELLS:
        pairs = ", ".join(
            f"{name}={value!r}" for name, value in zip(result.columns, first, strict=False)
        )
        return f"{purpose}: {pairs}"
    return f"{purpose}: {shape} over columns {', '.join(result.columns)}."


async def research(
    *,
    context: ToolContext,
    tools: ToolRegistry,
    events: EventWriter,
    state: ResearchState,
    budget: BudgetState,
    bundle: ContextBundle,
    graph: JoinGraph,
    dialect: str,
    checkpoint: Callable[[], Awaitable[None]],
    record_finding: Callable[[StateFinding], Awaitable[None]],
    settings: Settings | None = None,
) -> LoopOutcome:
    """Investigate until there is an answer or a ceiling says stop."""
    save = checkpoint
    previews: list[tuple[str, str]] = []

    for _ in range(budget.budget.iterations):
        stop = budget.exhausted()
        if stop is not None:
            state.stopped_by = stop.dimension
            state.phase = "finished"
            await save()
            await events.emit(
                "budget_exhausted", {"dimension": stop.dimension, "reason": stop.reason}
            )
            return LoopOutcome(
                ending="exhausted",
                caveat=stop.reason,
                execution_ids=state.execution_ids(),
                previews=tuple(previews),
            )

        warning = budget.approaching()
        if warning is not None:
            await events.emit("budget_warning", {"dimension": warning})

        budget.spend_iteration()
        state.iteration += 1
        state.phase = "planning"
        await save()
        await events.emit("step_started", {"iteration": state.iteration})

        plan, tokens = await _next_step(context, bundle, tools, state, settings)
        budget.spend_llm(tokens)
        await events.emit(
            "plan_created",
            {
                "purpose": plan.purpose,
                "answerable": plan.answerable,
                "iteration": state.iteration,
                "tokens": tokens,
            },
        )

        # The agent asked what a word means here (B-075, D-032).
        if wanted := _lookup_wanted(plan, state):
            bundle = await _look_up(
                context=context,
                tools=tools,
                events=events,
                state=state,
                bundle=bundle,
                term=wanted,
            )
            await save()
            # Costs this iteration and no model call beyond the plan that asked: nothing ran.
            continue

        if not plan.answerable:
            # A model's judgement is not a platform fact, and the two had the same finality (D-055).
            if not state.executions and not state.retried_judgement:
                state.retried_judgement = True
                state.judgement_reason = plan.reason
                await events.emit(
                    "plan_created",
                    {
                        "answerable": False,
                        "reason": plan.reason,
                        "retrying": True,
                    },
                )
                await save()
                continue
            state.phase = "finished"
            await save()
            return LoopOutcome(
                ending="refused",
                refusal=plan.reason or "The available data cannot answer that.",
                execution_ids=state.execution_ids(),
                previews=tuple(previews),
            )

        # Can these tables be joined at all?
        verdict = graph.check(tables_named(plan.sql, dialect=dialect))
        if not verdict.answerable:
            state.capability = verdict.as_payload()
            state.phase = "finished"
            await save()
            await events.emit("capability_checked", verdict.as_payload())
            return LoopOutcome(
                ending="refused",
                refusal=verdict.reason(),
                execution_ids=state.execution_ids(),
                previews=tuple(previews),
            )
        if verdict.chasms:
            # A chasm is recorded and not blocked, deliberately (D-026).
            state.capability = verdict.as_payload()
            await events.emit("capability_checked", verdict.as_payload())

        digest = proposed_hash(plan.sql)
        if state.has_run(digest):
            # Refused before it is sent: a loop going in circles pays nothing to do it.
            await events.emit(
                "reflection", {"continue": False, "public_rationale": "That query has already run."}
            )
            state.barren_iterations += 1
            if state.barren_iterations >= BARREN_LIMIT:
                return _no_progress(state, tuple(previews))
            continue

        state.phase = "executing"
        state.plan.append(Step(purpose=plan.purpose, sql=plan.sql, status="pending"))
        await save()

        result = await tools.call(
            context, "run_sql", {"sql": plan.sql, "purpose": plan.purpose}, events=events
        )
        budget.spend_query()

        progress = _Progress()
        if result.ok and isinstance(result.data, RunSqlOut):
            state.plan[-1].status = "done"
            summary = summarize(result.data, plan.purpose)
            state.record_execution(
                ExecutionRef(
                    execution_id=result.data.execution_id,
                    purpose=plan.purpose,
                    sql_hash=digest,
                    row_count=result.data.row_count,
                    rows_shown=len(result.data.rows),
                    summary=summary,
                    ok=True,
                    tables=list(result.data.tables),
                )
            )
            await events.emit(
                "query_executed",
                {
                    "execution_id": result.data.execution_id,
                    "row_count": result.data.row_count,
                    "duration_ms": result.data.duration_ms,
                    "masked_columns": result.data.masked_columns,
                },
            )
            await events.emit("result_summarized", {"one_liner": summary})
            previews.append((result.data.execution_id, result.render()))
            del previews[:-COMPOSE_PREVIEWS]
        else:
            # A refusal is recorded too, and this is what replaces WP7.2b's single explicit repair.
            state.plan[-1].status = "failed"
            state.record_execution(
                ExecutionRef(
                    execution_id="",
                    purpose=plan.purpose,
                    sql_hash=digest,
                    summary=f"refused ({result.code or 'unknown'}): {result.error}",
                    # Kept apart from `summary`, and only for a failure no rewrite could fix.
                    error="" if result.repairable else (result.error or ""),
                    ok=False,
                )
            )
            await events.emit(
                "sql_rejected", {"rule": result.code or "unknown", "repairable": result.repairable}
            )
            if not result.repairable:
                # WP7.2b's rule, kept: rewriting cannot fix a database that is down.
                state.phase = "finished"
                await save()
                return LoopOutcome(
                    ending="refused",
                    refusal=(
                        "I could not answer that from this data. The query could not "
                        f"be run: {result.error}"
                    ),
                    execution_ids=state.execution_ids(),
                    previews=tuple(previews),
                )

        state.phase = "observing"
        await save()

        reflection, tokens = await _reflect(context, bundle, state, plan, result, settings)
        budget.spend_llm(tokens)
        state.phase = "reflecting"

        # One claim per set of evidence, before anything is written (B-107).
        proposals = merge_by_evidence(
            [
                StateFinding(
                    statement=found.statement,
                    support=list(found.supported_by),
                    confidence=found.confidence,
                )
                for found in reflection.findings
            ]
        )
        for proposed in proposals:
            if state.add_finding(proposed):
                progress.findings_added += 1
                # The stored copy, whose citations have been filtered down to executions this...
                await record_finding(state.findings[-1])
        for question in reflection.open_questions:
            if question not in state.open_questions:
                state.open_questions.append(question)
                progress.questions_opened += 1

        state.barren_iterations = 0 if progress.moved else state.barren_iterations + 1
        await events.emit(
            "reflection",
            {"continue": not reflection.done, "public_rationale": reflection.rationale[:300]},
        )
        await save()

        if reflection.done:
            state.phase = "finished"
            await save()
            return LoopOutcome(
                ending="answered",
                execution_ids=state.execution_ids(),
                previews=tuple(previews),
            )

        if state.barren_iterations >= BARREN_LIMIT:
            return _no_progress(state, tuple(previews))

    # The `for` ran out: the iteration ceiling is the range.
    state.stopped_by = "iterations"
    state.phase = "finished"
    await save()
    await events.emit(
        "budget_exhausted", {"dimension": "iterations", "reason": "iteration ceiling"}
    )
    return LoopOutcome(
        ending="exhausted",
        caveat="I reached the maximum number of research steps for one question.",
        execution_ids=state.execution_ids(),
        previews=tuple(previews),
    )


def _no_progress(state: ResearchState, previews: tuple[tuple[str, str], ...]) -> LoopOutcome:
    """Two barren iterations in a row: finish with what there is (4.4)."""
    state.stopped_by = "no_progress"
    state.phase = "finished"
    return LoopOutcome(
        ending="no_progress",
        caveat="I stopped because the last few steps were not adding anything new.",
        execution_ids=state.execution_ids(),
        previews=previews,
    )


def _lookup_wanted(plan: Plan, state: ResearchState) -> str:
    """The term to look up, or empty when this step is not a lookup."""
    term = plan.define.strip()
    if not term:
        return ""
    if term.lower() in state.lookups:
        return ""
    if len(state.lookups) >= MAX_LOOKUPS:
        return ""
    return term


async def _look_up(
    *,
    context: ToolContext,
    tools: ToolRegistry,
    events: EventWriter,
    state: ResearchState,
    bundle: ContextBundle,
    term: str,
) -> ContextBundle:
    """Dispatch `search_knowledge` and put what it found in front of the next plan."""
    state.lookups.append(term.lower())
    result = await tools.call(
        context, "search_knowledge", {"query": term, "limit": LOOKUP_PASSAGES}, events=events
    )

    passages: list[PassageOut] = []
    note = ""
    if result.ok and isinstance(result.data, SearchKnowledgeOut):
        passages, note = result.data.passages, result.data.note

    for passage in passages:
        bundle = bundle.with_definition(
            Definition(term=term, text=passage.text, source=passage.source)
        )
    if passages:
        # Recorded only when the documents answered.
        state.prose_terms.append(term)

    await events.emit(
        "knowledge_consulted",
        {
            # The three facts a reader of the timeline needs: what was asked.
            "term": term,
            "passages": len(passages),
            "sources": [passage.source for passage in passages][:LOOKUP_PASSAGES],
            "found_by": sorted({passage.found_by for passage in passages}),
            # Empty on the happy path.
            "note": note,
        },
    )
    return bundle


async def _next_step(
    context: ToolContext,
    bundle: ContextBundle,
    tools: ToolRegistry,
    state: ResearchState,
    settings: Settings | None,
) -> tuple[Plan, int]:
    """The next query to run, from the same planner the single-shot path uses."""
    return await plan_query(
        org_id=context.org_id,
        bundle=bundle,
        registry=tools,
        role=context.role,
        run_id=context.run_id,
        actor_user_id=context.actor_user_id,
        settings=settings,
        # Two different things reach the planner through one parameter.
        repair_of="\n\n".join(
            part for part in (_progress_so_far(state), _nearest_question_ask(state)) if part
        )
        or None,
    )


#: What the one permitted second look actually asks for (D-055).
NEAREST_QUESTION_RULE = """You judged this question unanswerable, and gave this reason:

    {reason}

That may well be right about the question exactly as it was asked. Before
refusing, answer the nearest question this data *does* support — what can be
measured, what it costs, where it concentrates, how large it is — and say plainly
what you still cannot establish. Someone who asks whether X causes Y is usually
better served by what is measurable about X and Y, clearly labelled as not being
the causal answer, than by nothing at all.

If there is genuinely no such question, refuse again and name the gap. Do not pad
a refusal into an answer: an answer with nothing behind it is worse than the
refusal you already wrote."""


def _nearest_question_ask(state: ResearchState) -> str:
    """The retry's instruction, for the one attempt that follows the refusal."""
    if not state.retried_judgement or state.executions or not state.judgement_reason:
        return ""
    return NEAREST_QUESTION_RULE.format(reason=state.judgement_reason.strip())


def _progress_so_far(state: ResearchState) -> str:
    """What the planner is told about earlier iterations."""
    if not state.executions and not state.findings and not state.lookups:
        return ""
    lines = ["What you have already established in this investigation:"]
    for reference in state.executions:
        lines.append(f"- ran `{reference.purpose}` -> {reference.summary}")
    for finding in state.findings:
        lines.append(f"- concluded: {finding.statement}")
    if state.lookups:
        # Told, because a lookup it cannot see it already made is a lookup it will ask for again.
        lines.append(
            "- already looked up, and the answer is in the documents section of the "
            f"reference material above: {', '.join(sorted(state.lookups))}. Do not ask "
            "for these again; use what it says."
        )
    if state.open_questions:
        lines.append("Still open: " + "; ".join(state.open_questions))
    lines.append(
        "Write the next query that moves this forward. Do not repeat a query you "
        "have already run. If nothing further is needed, set answerable to false "
        "with reason 'complete'."
    )
    return "\n".join(lines)


async def _reflect(
    context: ToolContext,
    bundle: ContextBundle,
    state: ResearchState,
    plan: Plan,
    result: ToolResult,
    settings: Settings | None,
) -> tuple[Reflection, int]:
    """What did that tell us, and is there more worth doing?"""
    # The thread first and framed (D-029), for the reason the planner needs it too.
    thread = history_block(bundle.history)
    prompt = (
        (f"{thread}\n\n" if thread else "") + f"The question is: {state.question}\n\n"
        f"You have completed {state.iteration} research step(s).\n"
        f"{_progress_so_far(state) or 'Nothing established yet.'}\n\n"
        f"The step you just ran was for: {plan.purpose}\n"
        f"{result.render()}\n\n"
        "Record any finding this establishes, citing the execution id it came "
        "from. Say whether the question is now answered. If it is not, say what "
        "is still open. Keep the rationale to one short public sentence — it is "
        "shown to the person who asked."
    )
    from charie.agent.reviews import REVIEW_EVIDENCE, review_requested

    if review_requested(state.question):
        prompt += f"\n\n{REVIEW_EVIDENCE}"
    completion = await llm.complete(
        role="plan",
        org_id=context.org_id,
        messages=[Message(role="user", content=prompt)],
        schema=Reflection,
        run_id=context.run_id,
        actor_user_id=context.actor_user_id,
        settings=settings,
    )
    return completion.parsed_as(Reflection), completion.usage.total_tokens
