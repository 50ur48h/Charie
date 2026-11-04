"""The answer, and everything a reader needs to disbelieve it (arch 4.2, M9)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from charie.agent.capability import decode_inferred_joins
from charie.agent.coverage import Coverage, Period
from charie.agent.coverage import limitation as coverage_limitation
from charie.agent.critic import CriticVerdict
from charie.agent.provenance import caveat as provenance_caveat
from charie.agent.state import ExecutionRef, ResearchState
from charie.agent.tools.finalize import FinalizeIn

__all__ = [
    "ComposedAnswer",
    "assemble",
    "failed_executions",
    "failure_detail",
    "limitations_for",
]


@dataclass(frozen=True, slots=True)
class ComposedAnswer:
    """Architecture 4.2's `ComposedAnswer`, as much of it as Phase 9 fills."""

    text: str
    #: `answered` | `partly` | `refused`, derived by `run_state` (**D-044**).
    state: str
    #: The part of the question the run could not answer, in the composer's own words.
    unanswered: str
    confidence: str
    #: `query_executions.id` values, already verified to belong to this run.
    citations: tuple[str, ...] = ()
    #: One line on how the answer was reached, for a reader who will not read SQL.
    method: str = ""
    limitations: tuple[str, ...] = field(default_factory=tuple)


def method_note(state: ResearchState) -> str:
    """One sentence on how the answer was reached."""
    queries = sum(1 for reference in state.executions if reference.ok)
    if not queries:
        if state.executions:
            # B-095. A run that tried and was never answered is not a run that chose not to ask.
            attempted = len(state.executions)
            plural = "query" if attempted == 1 else "queries"
            return f"{attempted} {plural} tried against {_source_phrase(state)}; nothing came back."
        return "Answered without running a query."
    steps = max(state.iteration, 1)
    plural = "query" if queries == 1 else "queries"
    step_words = "one step" if steps == 1 else f"{steps} steps"
    return f"{queries} {plural} over {step_words}, against {_source_phrase(state)}."


def _source_phrase(state: ResearchState) -> str:
    names = [name.split(".")[-1] for name in state.table_names]
    if not names:
        return "this data source"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _prose_definitions(state: ResearchState) -> tuple[str, ...]:
    """Terms this run took from a document and nothing enforced (D-033)."""
    enforced = {name.lower().replace("_", " ") for name in state.applied_definitions}
    enforced |= {name.lower() for name in state.applied_definitions}
    return tuple(sorted({term for term in state.prose_terms if term.lower() not in enforced}))


def _and_list(names: tuple[str, ...]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


#: How many alternatives one note will name.
MAX_NAMED_ALTERNATIVES = 2


def _unused_sources(state: ResearchState) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The sources this answer read, and the ones it could have read and did not."""
    candidates = tuple(dict.fromkeys(state.candidate_sources))
    if len(candidates) < 2:
        return (), ()
    read = {table for reference in state.executions if reference.ok for table in reference.tables}
    used = tuple(name for name in candidates if name in read)
    unused = tuple(name for name in candidates if name not in read)
    if not used or not unused:
        return (), ()
    return used, unused


def failed_executions(state: ResearchState) -> tuple[ExecutionRef, ...]:
    """Queries that failed for a reason no rewrite could have fixed (B-095)."""
    return tuple(
        reference for reference in state.executions if not reference.ok and reference.error
    )


def failure_detail(state: ResearchState) -> str:
    """What the platform said went wrong, in its own already-sanitized words."""
    failures = failed_executions(state)
    return failures[-1].error if failures else ""


def _period(value: object) -> Period | None:
    """A `Period` back out of the trace payload's ``"a to b"`` (or ``"a"``) form."""
    if not isinstance(value, str) or not value:
        return None
    earliest, _, latest = value.partition(" to ")
    return Period(earliest=earliest, latest=latest or earliest)


def limitations_for(
    state: ResearchState,
    verdict: CriticVerdict | None,
    *,
    caveat: str = "",
    cited: Sequence[str] = (),
) -> tuple[str, ...]:
    """What this answer does not establish, in the order a reader needs it."""
    notes: list[str] = []

    # An answer that rests on a measured join says so (D-050).
    read: set[str] = set()
    for execution in state.executions:
        read.update(table.split(".")[-1].lower() for table in execution.tables)
    inferred_used = [
        (left, right)
        for left, right in decode_inferred_joins(state.capability.get("inferred"))
        if left.lower() in read and right.lower() in read
    ]
    if inferred_used:
        joins = "; ".join(f"{left} and {right}" for left, right in sorted(inferred_used))
        notes.append(
            f"This database does not declare how {joins} join. The link used here "
            f"was measured rather than declared — every value matched when the "
            f"catalog was built — so it reflects the data as it was then rather "
            f"than a rule the database enforces."
        )

    # What the definitions this run applied make the answer say (revision 0033).
    for name in state.applied_definitions:
        sentence = state.definition_caveats.get(name, "").strip()
        if sentence:
            notes.append(f"{name}: {sentence}")

    # Rows the model never saw (B-173).
    short = [
        execution
        for execution in state.executions
        if execution.execution_id in set(cited)
        and execution.ok
        and execution.row_count is not None
        and execution.rows_shown is not None
        and execution.rows_shown < execution.row_count
    ]
    if short:
        worst = max(short, key=lambda e: (e.row_count or 0) - (e.rows_shown or 0))
        many = f"{len(short)} of the queries behind this answer" if len(short) > 1 else "A query"
        notes.append(
            f"{many} returned more rows than could be shown to the model — "
            f"{worst.row_count} rows found, {worst.rows_shown} read. That is a limit of "
            "this platform, not of your data, so anything ranked or totalled here may "
            "be missing entries. Asking a narrower question returns the rest."
        )

    # Which rows this answer is made of (D-053, D-058, B-157).
    stated: object = state.capability.get("provenance")
    if isinstance(stated, dict):
        by_table = cast(dict[str, object], stated)
        sentence = provenance_caveat(
            {
                table: [str(mode) for mode in cast(list[object], modes)]
                for table, modes in by_table.items()
                if table.split(".")[-1].lower() in read and isinstance(modes, list)
            }
        )
        if sentence:
            notes.append(sentence)

    # The part of the question this data does not reach (D-051).
    asked: object = state.coverage.get("verdict")
    overlap: object = state.coverage.get("overlap")
    held: object = state.coverage.get("held")
    if asked == "partial" and isinstance(overlap, list) and isinstance(held, list):
        window = [str(end) for end in cast(list[object], overlap)]
        bounds = [str(end) for end in cast(list[object], held)]
        if len(window) == 2 and len(bounds) == 2:
            notes.append(
                f"This answer covers {window[0]} to {window[1]}, which is the part of the "
                f"period asked about that this database holds — it runs {bounds[0]} to "
                f"{bounds[1]}. The rest of the period asked for is not missing from the "
                f"answer; it is not in the data."
            )

    # What period this answer is actually about (B-157, D-059).
    coverage: object = state.capability.get("coverage")
    if isinstance(coverage, dict):
        stored = cast(dict[str, object], coverage)
        verdict_of_period = Coverage(
            status=str(stored.get("status", "")),
            reason=str(stored.get("reason", "")),
            answered=_period(stored.get("answered")),
            available=_period(stored.get("available")),
        )
        if sentence := coverage_limitation(verdict_of_period):
            notes.append(sentence)

    # First, and ahead of the budget caveat (D-034).
    if verdict is not None and verdict.blocked:
        notes.extend(
            f"A review of this answer did not pass, and it is shown anyway: {finding.detail}"
            for finding in verdict.blocking
        )

    if caveat:
        # The budget's own words. Already written for a person (`Exhaustion.reason`).
        notes.append(f"The investigation stopped before it was finished: {caveat}")

    if failures := failed_executions(state):
        # B-095, and it is B-087's distinction inverted.
        attempted = len(state.executions)
        if attempted == 1:
            count = "The one query this run tried failed to run"
        elif len(failures) == attempted:
            count = "Every query this run tried failed to run"
        else:
            count = f"{len(failures)} of the {attempted} queries this run tried failed to run"
        # Agreeing with the number that failed.
        subject = "it" if len(failures) == 1 else "they"
        notes.append(
            f"{count}, so nothing here rests on what {subject} would have returned: "
            f"{failure_detail(state)}"
        )

    if verdict is not None:
        notes.extend(finding.detail for finding in verdict.warnings)
        if verdict.verdict == "insufficient_evidence":
            notes.append(
                "A review judged the evidence insufficient to answer fully; what "
                "is here is the part the queries do support."
            )

    if unverified := _prose_definitions(state):
        # Prose informs the model; a structured definition binds it (D-033).
        terms = ", ".join(f"“{term}”" for term in unverified)
        notes.append(
            f"This answer relies on how your documents define {terms}. That "
            "definition was read as prose, so nothing checked that the query "
            "actually followed it — unlike a defined metric, which is enforced."
        )

    used, unused = _unused_sources(state)
    if used:
        # Stated, not judged. The claim is only that a choice existed and what it was between.
        named = list(unused[:MAX_NAMED_ALTERNATIVES])
        if len(unused) > MAX_NAMED_ALTERNATIVES:
            # Joined as a list item rather than appended as a clause: "a and b.
            named.append("others")
        notes.append(
            f"This answer reads {_and_list(used)}. The question also matched "
            f"{_and_list(tuple(named))} — tables with figures it could have been "
            "answered from, and not read here. A different source can give a "
            "different number."
        )

    thin = [
        reference
        for reference in state.executions
        if reference.ok and reference.row_count is not None and reference.row_count == 0
    ]
    if thin and len(thin) != len([r for r in state.executions if r.ok]):
        notes.append(
            f"{len(thin)} of the queries returned no rows, so any part of the "
            "answer resting on them is unsupported."
        )

    seen: set[str] = set()
    ordered: list[str] = []
    for note in notes:
        if note not in seen:
            seen.add(note)
            ordered.append(note)
    return tuple(ordered)


def assemble(
    draft: FinalizeIn,
    state: ResearchState,
    verdict: CriticVerdict | None,
    *,
    citations: tuple[str, ...],
    caveat: str = "",
) -> ComposedAnswer:
    """Everything the answer card renders, from what the run produced."""
    return ComposedAnswer(
        text=draft.answer,
        state=run_state(draft, citations),
        unanswered=draft.unanswered.strip(),
        confidence=_confidence(draft, verdict),
        citations=citations,
        method=method_note(state),
        limitations=limitations_for(state, verdict, caveat=caveat, cited=citations),
    )


#: The three endings a finished run can have.
RUN_STATES: Final = ("answered", "partly", "refused")


def run_state(draft: FinalizeIn, citations: tuple[str, ...]) -> str:
    """How this run ended — derived, never chosen (B-134, D-044)."""
    if not draft.unanswered.strip():
        return "answered"
    return "partly" if citations else "refused"


def _confidence(draft: FinalizeIn, verdict: CriticVerdict | None) -> str:
    """The model's own confidence, capped by what the review found (D-034)."""
    stated = draft.confidence if draft.confidence in {"high", "medium", "low"} else "medium"
    if verdict is not None and verdict.blocked and stated == "high":
        return "medium"
    return stated
