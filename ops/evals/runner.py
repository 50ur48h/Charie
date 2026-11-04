"""Run the twenty golden questions and say which ones are right (M9)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

#: Two homes, because this runs in two places.
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for candidate in (REPO_ROOT / "apps" / "api" / "src", REPO_ROOT / "apps" / "api" / "tests", HERE):
    if candidate.exists():
        sys.path.insert(0, str(candidate))

GOLDEN = HERE / "golden.yaml"
TRUTHS = next(
    path
    for path in (REPO_ROOT / "ops" / "seed" / "truths.json", HERE / "truths.json")
    if path.exists()
)

#: Pinned, and the reason is D-027. Two weeks past the seed's last row.
AS_OF = date(2026, 8, 16)

#: Live runs cost money. A run that has spent this much stops.
TOKEN_BUDGET = int(os.environ.get("EVALS_TOKEN_BUDGET", "400000"))


@dataclass
class Result:
    """One question's verdict, and enough to see why."""

    id: int
    question: str
    passed: bool = True
    failures: list[str] = field(default_factory=list["str"])
    answered: bool = False
    citations: int = 0
    iterations: int = 0
    queries: int = 0
    limitations: int = 0
    tokens: int = 0
    answer: str = ""
    #: What the critic said, when it said anything.
    critic: list[str] = field(default_factory=list["str"])
    #: Which rule matched the expected value (B-066).
    matched_by: str = ""
    #: True when the case allowed a refusal and got one.
    refused: bool = False
    #: The run's ending status.
    status: str = ""

    def fail(self, why: str) -> None:
        self.passed = False
        self.failures.append(why)


def truth_at(truths: dict[str, Any], path: str) -> Any:
    """Resolve a dotted path, with negative integers indexing from the end."""
    node: Any = truths
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def close_enough(got: Any, want: Any, tolerance: float) -> bool:
    """Numbers within tolerance; everything else compared as text."""
    try:
        left, right = float(got), float(want)
    except (TypeError, ValueError):
        return str(got).strip().lower() == str(want).strip().lower()
    if tolerance <= 0:
        return left == right
    scale = max(abs(right), 1.0)
    return abs(left - right) / scale <= tolerance


# --- Scripting the model ---


def script_for(case: dict[str, Any], fake: Any) -> None:
    """Teach the FakeLLM to answer this question, step by step."""
    from charie.agent.critic import CriticOut
    from charie.agent.loop import ReflectFinding, Reflection
    from charie.agent.planner import Plan

    steps = case["script"].get("steps")
    if steps is None:
        refusal = case["script"].get("refuse")
        if refusal is not None:
            fake.script(
                Plan(
                    sql="SELECT 1", purpose="check", answerable=False, reason=refusal
                ).model_dump_json(),
                role="sql",
                times=1,
            )
            return
        steps = [{"sql": case["script"]["sql"]}]

    for index, step in enumerate(steps):
        last = index == len(steps) - 1
        fake.script(
            Plan(
                sql=step["sql"], purpose=f"step {index + 1}", answerable=True, reason=""
            ).model_dump_json(),
            role="sql",
            times=1,
        )
        found = step.get("finding")
        fake.script(
            Reflection(
                findings=(
                    [ReflectFinding(statement=found, supported_by=[], confidence="medium")]
                    if found
                    else []
                ),
                open_questions=[],
                next_purpose="" if last else "keep going",
                done=last,
                rationale="that is enough" if last else "more to do",
            ).model_dump_json(),
            role="plan",
            times=1,
        )

    fake.script(_compose_from_prompt, role="compose", times=1)
    fake.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic", times=1)


_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _compose_from_prompt(request: Any) -> str:
    """Compose by citing whatever executions the prompt actually names."""
    import re

    from charie.agent.tools.finalize import FinalizeIn

    text = getattr(request, "prompt_text", "")
    ids = list(dict.fromkeys(re.findall(_UUID_PATTERN, text)))
    if not ids:
        raise AssertionError("the composing prompt named no execution")
    return FinalizeIn(
        answer=f"Answered from {len(ids)} query result(s).",
        supported_by=ids,
        confidence="high",
    ).model_dump_json()


# --- Running one question ---


async def resolve_target() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """The organization, data source and user to ask as."""
    from sqlalchemy import text

    from charie.datasources import service as datasources
    from charie.tenancy.session import org_session

    org_env = os.environ.get("EVALS_ORG_ID")
    if not org_env:
        raise SystemExit(
            "EVALS_ORG_ID is not set. The eval harness needs an organization with "
            "the pizza seed registered as a data source — `make up && make seed` "
            "and then register it, the same state `make agent.smoke` needs."
        )
    org_id = uuid.UUID(org_env)

    wanted = os.environ.get("EVALS_SOURCE", "Demo")
    sources = await datasources.list_data_sources(org_id)
    matching = [source for source in sources if source.name == wanted]
    if not matching:
        listed = ", ".join(source.name for source in sources) or "none"
        raise SystemExit(f"No data source named {wanted!r} in this org. There is: {listed}")

    async with org_session(org_id) as session:
        user_id = uuid.UUID(
            str(
                (
                    await session.execute(
                        text("SELECT user_id FROM org_memberships WHERE org_id = :o LIMIT 1"),
                        {"o": org_id},
                    )
                ).scalar_one()
            )
        )
    return org_id, matching[0].id, user_id


async def run_case(
    case: dict[str, Any],
    truths: dict[str, Any],
    target: tuple[uuid.UUID, uuid.UUID, uuid.UUID],
    *,
    live: bool,
) -> Result:
    """Ask one question through the whole stack and check what came back."""
    from sqlalchemy import text

    from charie.agent.runner import execute_run
    from charie.runs import service as runs
    from charie.tenancy.session import org_session

    org_id, source_id, user_id = target
    result = Result(id=case["id"], question=case["question"])

    settings = None
    if not live:
        from charie.llm.fake import FakeLLM
        from charie.llm.registry import clear_provider_cache, register_provider
        from llm_fixture import build_settings

        fake = FakeLLM()
        # A factory, not the instance: the registry builds providers on demand.
        clear_provider_cache()
        register_provider("fake", lambda: fake)
        script_for(case, fake)
        settings = build_settings()

    conversation = await runs.create_conversation(
        org_id=org_id, user_id=user_id, title=f"eval {case['id']}"
    )
    asked = await runs.post_message(
        org_id=org_id,
        user_id=user_id,
        conversation_id=conversation.id,
        content=case["question"],
        idempotency_key=uuid.uuid4().hex,
    )
    outcome = await execute_run(
        org_id=org_id,
        run_id=asked.run_id,
        data_source_id=source_id,
        actor_user_id=user_id,
        settings=settings,
        as_of=AS_OF,
    )

    # `state != "refused"`, not `state == "answered"` (D-044).
    result.answered = outcome.state != "refused"
    result.answer = outcome.answer
    result.status = outcome.status
    result.citations = len(outcome.execution_ids)
    result.iterations = outcome.iterations
    result.limitations = len(outcome.limitations)
    result.tokens = await tokens_spent(org_id, asked.run_id)
    result.critic = await critic_reasons(org_id, asked.run_id)

    async with org_session(org_id) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id::text AS id, sql_text, row_count, status "
                    "FROM query_executions WHERE run_id = :r ORDER BY created_at"
                ),
                {"r": asked.run_id},
            )
        ).all()
    result.queries = len(rows)

    artifacts = await artifacts_for(org_id, [row.id for row in rows])
    check_case(case, truths, result, rows, artifacts, live=live)
    return result


def check_case(
    case: dict[str, Any],
    truths: dict[str, Any],
    result: Result,
    rows: list[Any],
    artifacts: dict[str, dict[str, Any]],
    *,
    live: bool,
) -> None:
    """Every check the case declares, against what the run actually did."""
    expect = case.get("expect", {})

    # `may_refuse` is for a question with two right answers.
    result.refused = (
        bool(expect.get("may_refuse")) and not result.answered and result.status != "failed"
    )

    if expect.get("must_refuse"):
        if result.answered:
            result.fail("answered a question the schema cannot answer")
    elif result.refused:
        # A refusal that says nothing is not honesty, it is silence.
        if len(result.answer.strip()) < 20:
            result.fail("refused without saying why")
    elif not result.answered:
        # The critic's own words first: they say why.
        for reason in result.critic:
            result.fail(f"the critic blocked it: {reason}")
        if not result.critic:
            result.fail(f"did not answer: {result.answer[:120] or '(no answer was composed)'}")

    if "queries_run" in expect and result.queries != expect["queries_run"]:
        result.fail(f"ran {result.queries} queries, expected {expect['queries_run']}")

    # A refusal cites nothing by construction.
    if not result.refused and result.citations < expect.get("must_cite", 0):
        result.fail(f"cited {result.citations}, expected at least {expect.get('must_cite')}")

    if "min_iterations" in expect and result.iterations < expect["min_iterations"]:
        result.fail(f"took {result.iterations} steps, expected at least {expect['min_iterations']}")

    if "limitations_min" in expect and result.limitations < expect["limitations_min"]:
        result.fail(f"carried {result.limitations} limitations, expected more")

    executed = " ".join(row.sql_text for row in rows)
    for needle in expect.get("sql_contains", []):
        if needle not in executed:
            result.fail(f"no query mentioned {needle!r}")
    for banned in expect.get("sql_excludes", []):
        if banned in executed:
            result.fail(f"a query used {banned!r}, which D-027 forbids")

    phrase = expect.get("answer_contains")
    if live and phrase and phrase.lower() not in result.answer.lower():
        result.fail(f"the answer never said {phrase!r}")

    # The value checks are skipped for an allowed refusal.
    if not result.refused:
        # `truth_any` is a list of paths, any of which is a right answer.
        paths = case.get("truth_any") or ([case["truth"]] if "truth" in case else [])
        if paths and (column := expect.get("value_of")):
            _check_value(
                result,
                artifacts,
                column,
                [truth_at(truths, path) for path in paths],
                float(case.get("tolerance", 0)),
            )
        if "value_is" in expect and (column := expect.get("value_of")):
            _check_value(result, artifacts, column, expect["value_is"], 0)

    if "rows" in expect:
        counts = [row.row_count for row in rows if row.status == "ok"]
        if expect["rows"] not in counts:
            result.fail(f"no query returned {expect['rows']} rows; got {counts}")


def _check_value(
    result: Result,
    artifacts: dict[str, dict[str, Any]],
    column: str,
    want: Any,
    tolerance: float,
) -> None:
    """Compare one expected value, and say how it was found (B-066)."""
    match = match_value(artifacts, column, want, tolerance)
    result.matched_by = match.how
    wanted = " or ".join(
        repr(candidate) for candidate in (want if isinstance(want, list) else [want])
    )
    if match.how == "absent":
        shapes = ", ".join(match.shapes) or "(no result returned any rows)"
        result.fail(f"{wanted} was in no result; the results returned {shapes}")
    elif not match.ok:
        result.fail(f"{column} was {match.seen!r}, expected {wanted}")


#: How many columns a single-row result may have before the harness stops scanning its cells.
MAX_SCAN_COLUMNS = 4


@dataclass(frozen=True)
class ValueMatch:
    """Whether the expected value is in the results, and how it was found."""

    ok: bool
    #: column | only-value | row-cell | absent
    how: str
    seen: Any = None
    #: Every result's column names, for a failure message that can be acted on.
    shapes: tuple[str, ...] = ()

    @property
    def weaker(self) -> bool:
        """True when the exact column was not there and a fallback found it."""
        return self.ok and self.how != "column"


def match_value(
    artifacts: dict[str, dict[str, Any]],
    column: str,
    want: Any,
    tolerance: float,
) -> ValueMatch:
    """Is ``want`` among the results, under the name the case expects or not?"""
    frames = [(frame.get("columns") or [], frame.get("rows") or []) for frame in artifacts.values()]
    shapes = tuple(f"[{', '.join(str(name) for name in names)}]" for names, _ in frames)
    wants = want if isinstance(want, list) else [want]

    def any_of(seen: Any) -> bool:
        return any(close_enough(seen, candidate, tolerance) for candidate in wants)

    wanted = column.strip().lower()
    for names, rows in frames:
        lowered = [str(name).strip().lower() for name in names]
        if wanted in lowered and rows:
            seen = rows[0][lowered.index(wanted)]
            return ValueMatch(any_of(seen), "column", seen, shapes)

    for names, rows in frames:
        if len(names) == 1 and len(rows) == 1 and any_of(rows[0][0]):
            return ValueMatch(True, "only-value", rows[0][0], shapes)

    for names, rows in frames:
        if len(rows) != 1 or not 1 < len(names) <= MAX_SCAN_COLUMNS:
            continue
        for seen in rows[0]:
            if any_of(seen):
                return ValueMatch(True, "row-cell", seen, shapes)

    return ValueMatch(False, "absent", None, shapes)


async def critic_reasons(org_id: uuid.UUID, run_id: uuid.UUID) -> list[str]:
    """Every blocking finding the critic recorded, newest verdict last."""
    from charie.runs.events import read_events

    reasons: list[str] = []
    for event in await read_events(org_id=org_id, run_id=run_id):
        if event.type != "critic_verdict":
            continue
        findings = event.payload.get("findings") or []
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if isinstance(finding, dict) and finding.get("severity") == "block":
                reasons.append(str(finding.get("detail", "")))
    return reasons


async def tokens_spent(org_id: uuid.UUID, run_id: uuid.UUID) -> int:
    """What this run cost, from the ledger rather than from anyone's tally."""
    from sqlalchemy import text

    from charie.tenancy.session import org_session

    async with org_session(org_id) as session:
        total = (
            await session.execute(
                text(
                    "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) "
                    "FROM usage_ledger WHERE run_id = :r"
                ),
                {"r": run_id},
            )
        ).scalar_one()
    return int(total or 0)


async def artifacts_for(org_id: uuid.UUID, execution_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Every stored result for this run, keyed by execution."""
    if not execution_ids:
        return {}

    from sqlalchemy import text

    from charie.tenancy.session import org_session

    async with org_session(org_id) as session:
        rows = (
            await session.execute(
                text(
                    "SELECT query_execution_id::text AS id, summary, sample_rows "
                    "FROM result_artifacts WHERE query_execution_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": execution_ids},
            )
        ).all()
    return {
        row.id: {
            "columns": list((row.summary or {}).get("columns") or []),
            "rows": list(row.sample_rows or []),
            "masked": list((row.summary or {}).get("masked_columns") or []),
        }
        for row in rows
    }


# --- The suite ---


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", type=int, nargs="*", help="Run just these ids")
    parser.add_argument("--json", action="store_true", help="Machine-readable summary")
    args = parser.parse_args(argv)

    import yaml
    from dotenv import load_dotenv

    if (env := REPO_ROOT / ".env").exists():
        load_dotenv(env)
    live = os.environ.get("EVALS_LIVE") == "1"

    cases = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    truths = json.loads(TRUTHS.read_text(encoding="utf-8"))
    if args.only:
        cases = [case for case in cases if case["id"] in args.only]

    target = await resolve_target()
    mode = "LIVE — real models, real money" if live else "FakeLLM — deterministic"
    print(f"{len(cases)} golden questions · {mode} · as_of {AS_OF}\n")

    results: list[Result] = []
    spent = 0
    for case in cases:
        # Checked before the question, not after.
        if live and spent >= TOKEN_BUDGET:
            print(f"\n  stopped: {spent:,} tokens against a budget of {TOKEN_BUDGET:,}")
            break
        try:
            outcome = await run_case(case, truths, target, live=live)
        except Exception as error:
            outcome = Result(id=case["id"], question=case["question"])
            outcome.fail(f"{type(error).__name__}: {error}")
        spent += outcome.tokens
        results.append(outcome)
        mark = "PASS" if outcome.passed else "FAIL"
        cost = f"  {outcome.tokens:>7,} tok" if live else ""
        print(f"  [{mark}] {outcome.id:>2}. {outcome.question[:56]}{cost}")
        # A pass earned by a weaker rule is a weaker claim.
        if outcome.matched_by in {"only-value", "row-cell"}:
            print(f"          (value matched by {outcome.matched_by}, not by column name)")
        if outcome.refused:
            print("          (refused, which this question allows)")
        for why in outcome.failures:
            print(f"          {why}")

    passed = sum(1 for outcome in results if outcome.passed)
    tail = f" · {spent:,} tokens" if live else ""
    print(f"\n{passed}/{len(results)} passed{tail}")
    if len(results) < len(cases):
        # An unasked question is not a passing one.
        print(f"{len(cases) - len(results)} question(s) were never asked")
        return 1
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": r.id,
                        "passed": r.passed,
                        "failures": r.failures,
                        "citations": r.citations,
                        "iterations": r.iterations,
                        "queries": r.queries,
                        "limitations": r.limitations,
                    }
                    for r in results
                ],
                indent=1,
            )
        )
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
