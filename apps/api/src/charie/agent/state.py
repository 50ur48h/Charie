"""What a run knows about itself (architecture 4.2), and what survives a restart."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ExecutionRef",
    "Hypothesis",
    "ResearchState",
    "StateFinding",
    "Step",
    "merge_by_evidence",
]

#: Where the loop is. Named after 4.4's state diagram so the trace.
Phase = Literal[
    "starting",
    "context",
    "planning",
    "executing",
    "observing",
    "reflecting",
    "validating",
    "composing",
    "finished",
]


class ExecutionRef(BaseModel):
    """A query this run ran, and one line about what came back.

    The summary is what the next prompt sees; the id is what a citation resolves
    through. Rows appear in neither — they are in `result_artifacts`, masked, one
    HTTP call away for a person who wants them (B-034).
    """

    model_config = ConfigDict(extra="forbid")

    execution_id: str
    purpose: str = ""
    #: Identifies what was asked of the database, so asking it again can be recognised and refused.
    sql_hash: str = ""
    #: The tables this statement read, as the validator resolved them.
    tables: list[str] = Field(default_factory=list[str])
    row_count: int | None = None
    #: How many of `row_count` the model was actually shown.
    rows_shown: int | None = None
    summary: str = ""
    ok: bool = True
    #: Why this query never returned, in the connector's own sanitized words.
    error: str = ""


class StateFinding(BaseModel):
    """Something the run concluded, and the executions that back it."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    support: list[str] = Field(default_factory=list[str])
    confidence: str = "medium"


#: Weakest first. A merged claim is only as strong as its least certain part.
_CONFIDENCE_ORDER = ("low", "medium", "high")


def merge_by_evidence(findings: Sequence[StateFinding]) -> list[StateFinding]:
    """Findings from one reflection resting on the same executions, as one claim."""
    merged: list[StateFinding] = []
    at: dict[tuple[str, ...], int] = {}
    for finding in findings:
        key = tuple(sorted(finding.support))
        if not key or key not in at:
            if key:
                at[key] = len(merged)
            merged.append(finding)
            continue
        held = merged[at[key]]
        statement = held.statement.rstrip()
        if not statement.endswith((".", "!", "?", ":", ";")):
            statement += "."
        merged[at[key]] = held.model_copy(
            update={
                "statement": f"{statement} {finding.statement.lstrip()}",
                "confidence": min(
                    (held.confidence, finding.confidence),
                    key=lambda word: (
                        _CONFIDENCE_ORDER.index(word) if word in _CONFIDENCE_ORDER else 1
                    ),
                ),
            }
        )
    return merged


class Hypothesis(BaseModel):
    """A thing the run is trying to establish, and where it got to."""

    model_config = ConfigDict(extra="forbid")

    text: str
    status: Literal["open", "supported", "rejected"] = "open"
    tested_by: list[str] = Field(default_factory=list[str])


class Step(BaseModel):
    """One plan step. Small and re-plannable, per 4.3."""

    model_config = ConfigDict(extra="forbid")

    purpose: str
    sql: str = ""
    status: Literal["pending", "done", "failed", "skipped"] = "pending"


class ResearchState(BaseModel):
    """Architecture 4.2's state, as much of it as Phase 8 fills in.

    Fields 4.2 names that later work packages own are present and empty rather
    than absent — `capability` is WP8.2's, `critic` is WP9.1's — so the shape a
    checkpoint round-trips does not change underneath a run that is already
    stored. A field that appears later would make every state written before it
    unreadable by the code that reads them.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    org_id: uuid.UUID
    question: str = ""
    #: The date this run resolved "last month" against (D-027).
    as_of: str = ""

    phase: Phase = "starting"
    iteration: int = 0

    table_names: list[str] = Field(default_factory=list[str])
    plan: list[Step] = Field(default_factory=list[Step])
    executions: list[ExecutionRef] = Field(default_factory=list[ExecutionRef])
    findings: list[StateFinding] = Field(default_factory=list[StateFinding])
    hypotheses: list[Hypothesis] = Field(default_factory=list[Hypothesis])
    open_questions: list[str] = Field(default_factory=list[str])

    #: WP8.2's join-path verdicts and WP9.1's verdict — both written now.
    capability: dict[str, Any] = Field(default_factory=dict[str, Any])
    #: What period the question asked for, against what the data holds (D-051).
    coverage: dict[str, Any] = Field(default_factory=dict[str, Any])
    #: Whether the one permitted retry of a model-judgement refusal has been spent (D-055).
    retried_judgement: bool = False
    #: What the planner said when it first judged the question unanswerable.
    judgement_reason: str = ""
    critic: dict[str, Any] | None = None

    #: How many drafts the critic has judged.
    critic_passes: int = 0

    #: Terms this run has looked up in the organization's documents (B-075, D-032), lowercased.
    lookups: list[str] = Field(default_factory=list[str])

    #: Of those, the terms the documents actually had something to say about (D-033).
    prose_terms: list[str] = Field(default_factory=list[str])

    #: Semantic definitions this question matched and the critic therefore enforces.
    applied_definitions: list[str] = Field(default_factory=list[str])
    #: What each applied definition makes the answer say (revision 0033).
    definition_caveats: dict[str, str] = Field(default_factory=dict[str, str])

    #: How many active definitions this data source had when the question was asked (B-087).
    definitions_available: int = 0
    #: The tables this question retrieved that have figures to aggregate.
    candidate_sources: list[str] = Field(default_factory=list[str])

    #: Set when a ceiling stopped the run, so the composed answer can say which.
    stopped_by: str | None = None
    #: How many consecutive iterations added nothing.
    barren_iterations: int = 0

    def execution_ids(self) -> tuple[str, ...]:
        """The ids a citation may name — successful executions only."""
        return tuple(
            reference.execution_id
            for reference in self.executions
            if reference.ok and reference.execution_id
        )

    def every_query_failed(self) -> bool:
        """Queries were attempted and not one of them came back (B-095)."""
        return bool(self.executions) and not any(reference.ok for reference in self.executions)

    def has_run(self, sql_hash: str) -> bool:
        """Whether this exact statement has already been sent (4.4)."""
        return bool(sql_hash) and any(
            reference.sql_hash == sql_hash for reference in self.executions
        )

    def record_execution(self, reference: ExecutionRef) -> None:
        self.executions.append(reference)

    def add_finding(self, finding: StateFinding) -> bool:
        """Keep a finding, dropping citations this run did not produce."""
        real = [item for item in finding.support if item in self.execution_ids()]
        if finding.support and not real:
            return False
        if any(
            existing.statement.strip() == finding.statement.strip() for existing in self.findings
        ):
            # The same sentence twice is not progress.
            return False
        if real and any(sorted(existing.support) == sorted(real) for existing in self.findings):
            # Restated on evidence this run has already concluded from.
            return False
        self.findings.append(finding.model_copy(update={"support": real}))
        return True

    def as_json(self) -> dict[str, Any]:
        """The checkpoint written to `agent_runs.state` at every transition."""
        return self.model_dump(mode="json")

    @classmethod
    def restore(cls, payload: Any) -> Self | None:
        """Read a checkpoint back, or None if it is not one."""
        if not isinstance(payload, dict):
            return None
        try:
            return cls.model_validate(payload)
        except Exception:
            return None
