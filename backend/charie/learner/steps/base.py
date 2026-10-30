"""Learning steps: what they are, and the context they run in (P07.1)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.tables.sources import DataSource

# Architecture 02's canonical order. Steps register in this order; the feed
# numbers them 1-12, and totals count only registered steps.
CANONICAL_ORDER = (
    "owner_notes",
    "structure",
    "profile",
    "links",
    "documents",
    "doc_facts",
    "explain_tables",
    "business_numbers",
    "defaults",
    "owner_questions",
    "self_test",
    "readiness",
)

STEP_NUMBERS = {name: number + 1 for number, name in enumerate(CANONICAL_ORDER)}


@dataclass(frozen=True)
class StepContext:
    """What a step handler gets: the run, its version, and how to talk."""

    session: Session
    run_id: int
    version_id: int
    source: DataSource | None
    connector: PostgresConnector | None
    strict_mode: bool
    settings: dict[str, Any]
    say: Callable[[str, str, dict[str, Any]], None]


@dataclass(frozen=True)
class Step:
    """One learning step: its jobs, its work, its finish."""

    name: str
    title: str
    job_kind: str
    make_jobs: Callable[[StepContext], list[dict[str, Any]]]
    run_job: Callable[[Any, StepContext], None]
    finish: Callable[[StepContext], None] = lambda ctx: None


STEPS: dict[str, Step] = {}


def register_step(step: Step) -> Step:
    """Register a step in canonical order; registering twice is refused."""
    if step.name not in CANONICAL_ORDER:
        raise ValueError(f"Step `{step.name}` is not one of the 12 learning steps.")
    if step.name in STEPS:
        raise ValueError(f"Step `{step.name}` is already registered.")
    STEPS[step.name] = step
    ordered = {name: STEPS[name] for name in CANONICAL_ORDER if name in STEPS}
    STEPS.clear()
    STEPS.update(ordered)
    return step


def step_number(name: str) -> int:
    """The 1-12 feed number for a step name."""
    return STEP_NUMBERS[name]
