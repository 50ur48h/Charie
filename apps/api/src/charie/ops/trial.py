"""An engine trial: point the product at an unfamiliar dataset and see where it breaks."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

from sqlalchemy import select

from charie.agent.runner import execute_run
from charie.db.models import AgentRun, QueryExecution
from charie.runs import service as runs
from charie.tenancy.session import org_session

#: Three, and the floor is enforced.
MINIMUM_REPEATS: Final = 3

#: Numbers in an answer, for the coarse "did they say the same thing" check.
_NUMBER = re.compile(r"\d[\d,]*\.?\d*")


@dataclass(frozen=True, slots=True)
class ProbeRun:
    """One run of one probe. Everything a person needs to judge it, and no prose."""

    run_id: uuid.UUID
    status: str
    #: `answered` | `partly` | `refused`, or None for a run that predates D-044.
    state: str | None
    #: What the run could not answer, when it named something.
    unanswered: str
    answer: str
    #: What context offered that had figures to aggregate.
    sources_offered: tuple[str, ...]
    tables_read: tuple[str, ...]
    statements: tuple[str, ...]
    limitations: tuple[str, ...]
    method: str
    findings: int

    @property
    def ending(self) -> str:
        """What to call this run in a report."""
        return self.state if self.status == "completed" and self.state else self.status


@dataclass(frozen=True, slots=True)
class ProbeResult:
    question: str
    runs: tuple[ProbeRun, ...]
    divergences: tuple[str, ...] = field(default_factory=tuple)


def _figures(answer: str) -> tuple[str, ...]:
    """The numbers an answer states, normalised for comparison."""
    return tuple(sorted({match.group(0).replace(",", "") for match in _NUMBER.finditer(answer)}))


def divergences(runs: tuple[ProbeRun, ...]) -> tuple[str, ...]:
    """Where the runs of one probe disagree."""
    found: list[str] = []

    endings = Counter(r.ending for r in runs)
    if len(endings) > 1:
        found.append(
            "the runs ended differently: "
            + ", ".join(f"{count}x {name}" for name, count in sorted(endings.items()))
            + " — a question that refuses sometimes and answers other times is B-119's shape"
        )

    read = {r.tables_read for r in runs}
    if len(read) > 1:
        found.append(
            "they read different tables: "
            + " | ".join(", ".join(t) or "(none)" for t in sorted(read))
            + " — two defensible sources for one question is B-060's shape"
        )

    figures = {_figures(r.answer) for r in runs if r.answer}
    if len(figures) > 1:
        found.append(
            "they stated different numbers: "
            + " | ".join(", ".join(f) or "(none)" for f in sorted(figures))
            + " — check whether the difference is the answer or the wording"
        )

    counts = {len(r.statements) for r in runs}
    if len(counts) > 1:
        found.append(
            f"they ran different numbers of queries: {sorted(counts)} — not a defect by "
            "itself, and worth reading beside the rest"
        )

    return tuple(found)


async def _record(org_id: uuid.UUID, run_id: uuid.UUID) -> ProbeRun:
    """Read back what the run actually did, from the platform's own rows."""
    view = await runs.get_run(org_id=org_id, run_id=run_id)

    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    select(QueryExecution)
                    .where(QueryExecution.run_id == run_id)
                    .order_by(QueryExecution.created_at)
                )
            )
            .scalars()
            .all()
        )
        # From the run's checkpoint, because `RunView` does not carry it.
        state = (
            await session.execute(select(AgentRun.state).where(AgentRun.id == run_id))
        ).scalar_one_or_none()

    tables: list[str] = []
    for row in rows:
        for table in row.tables:
            if table not in tables:
                tables.append(table)

    return ProbeRun(
        run_id=run_id,
        status=view.status,
        state=view.state,
        unanswered=view.unanswered,
        answer=view.answer or "",
        sources_offered=tuple(offered_sources(state)),
        tables_read=tuple(sorted(tables)),
        statements=tuple(row.sql_text for row in rows),
        limitations=tuple(view.limitations),
        method=view.method,
        findings=len(view.findings),
    )


def offered_sources(state: object) -> list[str]:
    """What context offered that had figures to aggregate (B-093)."""
    if not isinstance(state, dict):
        return []
    stored = cast("dict[str, object]", state)
    candidates = stored.get("candidate_sources")
    if not isinstance(candidates, list):
        return []
    return sorted(str(candidate) for candidate in cast("list[object]", candidates))


async def run_probe(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    data_source_id: uuid.UUID,
    question: str,
    repeats: int,
) -> ProbeResult:
    """Ask one question `repeats` times and compare the runs."""
    if repeats < MINIMUM_REPEATS:
        raise ValueError(
            f"repeats={repeats} is below the floor of {MINIMUM_REPEATS}. One run of "
            "B-119's question came back clean on 2026-08-25 against a build whose "
            "prompt path was unchanged, so a single-shot trial would have closed a "
            "live P1. Asking once measures the model's luck on the day."
        )

    records: list[ProbeRun] = []
    for _ in range(repeats):
        asked = await runs.post_message(
            org_id=org_id,
            user_id=user_id,
            conversation_id=conversation_id,
            content=question,
            idempotency_key=uuid.uuid4().hex,
        )
        await execute_run(
            org_id=org_id,
            run_id=asked.run_id,
            data_source_id=data_source_id,
            actor_user_id=user_id,
        )
        records.append(await _record(org_id, asked.run_id))

    runs_tuple = tuple(records)
    return ProbeResult(question=question, runs=runs_tuple, divergences=divergences(runs_tuple))


def render(results: list[ProbeResult]) -> str:
    """The report. Divergences first, because they are the reason to read it."""
    lines: list[str] = []
    flagged = [r for r in results if r.divergences]

    lines.append(f"trial: {len(results)} probe(s), {len(flagged)} with disagreements")
    lines.append("")

    if flagged:
        lines.append("=== where the runs disagreed ===")
        for result in flagged:
            lines.append(f"  {result.question}")
            for note in result.divergences:
                lines.append(f"    - {note}")
        lines.append("")

    lines.append("=== every run ===")
    for result in results:
        lines.append(f"  {result.question}")
        for index, run in enumerate(result.runs, start=1):
            ending = run.ending
            lines.append(
                f"    {index}. {ending}  tables={','.join(run.tables_read) or '-'}  "
                f"queries={len(run.statements)}  findings={run.findings}"
            )
            if run.answer:
                lines.append(f"       {run.answer[:160]}")
            for limitation in run.limitations:
                lines.append(f"       caveat: {limitation[:140]}")
        lines.append("")

    return "\n".join(lines)


async def run_trial(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    probes: list[str],
    repeats: int,
) -> str:
    """Every probe, in one conversation, rendered."""
    conversation = await runs.create_conversation(
        org_id=org_id, user_id=user_id, title="engine trial", data_source_id=source_id
    )

    results = [
        await run_probe(
            org_id=org_id,
            user_id=user_id,
            conversation_id=conversation.id,
            data_source_id=source_id,
            question=question,
            repeats=repeats,
        )
        for question in probes
    ]
    return render(results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="Organization id.")
    parser.add_argument("--user", required=True, help="Actor user id.")
    parser.add_argument("--source", required=True, help="Data source id to ask against.")
    parser.add_argument("--probes", required=True, help="JSON file: a list of questions.")
    parser.add_argument(
        "--repeats",
        type=int,
        default=MINIMUM_REPEATS,
        help=f"Runs per probe. Refused below {MINIMUM_REPEATS} — see the module docstring.",
    )
    parser.add_argument("--out", help="Also write the report here.")
    args = parser.parse_args()

    probes: list[str] = json.loads(Path(args.probes).read_text(encoding="utf-8"))
    report = asyncio.run(
        run_trial(
            org_id=uuid.UUID(args.org),
            user_id=uuid.UUID(args.user),
            source_id=uuid.UUID(args.source),
            probes=probes,
            repeats=args.repeats,
        )
    )
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nwritten to {args.out}")

    # Exit 0 even when probes disagreed.


if __name__ == "__main__":
    main()
