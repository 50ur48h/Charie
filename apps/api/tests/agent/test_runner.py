"""The ends of a run: asked, investigated, answered or honestly refused."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, date, datetime
from typing import cast

import pytest
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine

from charie.agent.budget import DEFAULT_ITERATIONS
from charie.agent.critic import CriticOut
from charie.agent.loop import ReflectFinding, Reflection
from charie.agent.planner import Plan
from charie.agent.runner import COMPOSE_OUTPUT_TOKENS, RunOutcome, execute_run
from charie.agent.tools.base import ToolContext
from charie.agent.tools.finalize import FinalizeIn
from charie.llm.base import LLMError
from charie.llm.fake import FakeLLM
from charie.runs import service as runs
from charie.runs.events import read_events
from llm_fixture import build_settings


def _plan(sql: str, *, answerable: bool = True, reason: str = "") -> str:
    return Plan(
        sql=sql, purpose="answer the question", answerable=answerable, reason=reason
    ).model_dump_json()


def _reflect(
    *,
    done: bool = True,
    findings: list[ReflectFinding] | None = None,
    open_questions: list[str] | None = None,
) -> str:
    """One reflection. `done=True` makes the loop a single iteration."""
    return Reflection(
        findings=findings or [],
        open_questions=open_questions or [],
        next_purpose="",
        done=done,
        rationale="that answers it",
    ).model_dump_json()


def _final(answer: str, *, unanswered: str = "", cite: list[str] | None = None) -> str:
    return FinalizeIn(
        answer=answer, unanswered=unanswered, supported_by=cite or [], confidence="high"
    ).model_dump_json()


def _passes() -> str:
    """A critic that finds nothing."""
    return CriticOut(verdict="pass", reasons=[]).model_dump_json()


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _reflects_citing_the_execution(request: object) -> str:
    """Reflect with a finding that cites the execution just run."""
    text_of = getattr(request, "prompt_text", "")
    found = _UUID.search(text_of)
    assert found is not None, f"the reflecting prompt named no execution: {text_of}"
    return _reflect(
        findings=[
            ReflectFinding(statement="Shop counts are available.", supported_by=[found.group(0)])
        ]
    )


def _cites_the_execution(request: object) -> str:
    """Compose by reading the execution id out of the prompt it was given."""
    text_of = getattr(request, "prompt_text", "")
    found = _UUID.search(text_of)
    assert found is not None, f"the composing prompt named no execution: {text_of}"
    return _final("There are 3 shops.", cite=[found.group(0)])


async def _run_for(context: ToolContext, question: str) -> uuid.UUID:
    """A fresh queued run in the fixture's conversation."""
    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)
    asked = await runs.post_message(
        org_id=context.org_id,
        user_id=context.actor_user_id or uuid.uuid4(),
        conversation_id=view.conversation_id,
        content=question,
        idempotency_key=uuid.uuid4().hex,
    )
    return asked.run_id


async def _execute(context: ToolContext, run_id: uuid.UUID) -> RunOutcome:
    return await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
    )


async def _types(context: ToolContext, run_id: uuid.UUID) -> list[str]:
    return [e.type for e in await read_events(org_id=context.org_id, run_id=run_id)]


# --- The happy path ---


async def test_a_question_becomes_sql_rows_and_a_cited_answer(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The M7 criterion end to end: asked, answered, and the answer cites a real execution row."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    outcome = await _execute(context, run_id)

    assert outcome.status == "completed"
    assert outcome.state == "answered"
    assert outcome.iterations == 1, "one step was enough, so one step is what it took"
    assert outcome.stopped_by is None, "nothing cut this short"
    assert len(outcome.execution_ids) == 1

    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.status == "completed"
    assert view.answer == "There are 3 shops."
    assert view.finished_at is not None
    # The finding is the citation, and it names the row the DAL really wrote.
    assert len(view.findings) == 1
    assert view.findings[0].support == list(outcome.execution_ids)
    # B-100. Architecture 4.2's fourth part of an answer.
    assert view.method.startswith("1 query over one step"), view.method
    # The control for B-133.
    assert view.state == "answered"


async def test_the_composer_is_told_to_write_something_a_person_can_read(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """B-172, and the half that is easy to get wrong."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    await _execute(context, run_id)

    composing = " ".join(fake_llm.prompts(role="compose"))
    assert composing, "no composing call was made, so this proves nothing"
    assert "Write the answer as Markdown" in composing
    assert "Never run a ranked list through a sentence with commas" in composing
    assert "Use everyday words and short sentences" in composing
    # Simple is not vague: the rule must not read as licence to drop numbers.
    assert "keep every number, every name and every limit" in composing

    # B-179 and B-180, in the same prompt and for the same reader.
    assert "USD 310,817" in composing
    assert "Do not guess a currency" in composing
    assert "something a person could start this week" in composing
    assert "wearing a recommendation" in composing

    planning = " ".join(fake_llm.prompts(role="sql")) + " ".join(fake_llm.prompts(role="plan"))
    assert "Write the answer as Markdown" not in planning, (
        "the formatting rule belongs to the composer; a planner told to use "
        "bullet points is paying for advice about a job it does not do"
    )


async def test_a_rephrased_answer_is_not_a_second_finding(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """B-096. The Phase 7 rule is one claim once."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    # The loop reaches a finding of its own, in its own words.
    fake_llm.script(_reflects_citing_the_execution, role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    await _execute(context, run_id)

    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    statements = [finding.statement for finding in view.findings]
    assert len(view.findings) == 1, (
        f"the same claim was recorded twice, in two phrasings: {statements}"
    )


async def test_a_genuinely_new_claim_still_becomes_a_finding(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The other side of B-096, so the fix cannot be "record nothing"."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    outcome = await _execute(context, run_id)

    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert len(view.findings) == 1
    assert view.findings[0].support == list(outcome.execution_ids)


async def test_the_trace_tells_the_whole_story_in_order(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """A trace that skips a step is worse than none: it looks complete."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    await _execute(context, run_id)

    assert await _types(context, run_id) == [
        "run_started",
        "context_selected",
        # The join graph is checked once, up front.
        "capability_checked",
        # One iteration, and every stage of it is visible.
        "step_started",
        "plan_created",
        "tool_called",
        "query_executed",
        "result_summarized",
        "reflection",
        # The draft is judged before it becomes the answer (WP9.1).
        "critic_verdict",
        "answer_composed",
        # The finding is written after the answer and before the ending.
        "finding_added",
        "run_finished",
    ]


async def test_the_execution_row_is_attributed_to_this_run(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    outcome = await _execute(context, run_id)

    engine = create_async_engine(wired)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"),
                {"org": str(context.org_id)},
            )
            rows = (
                await connection.execute(
                    text("SELECT id, status FROM query_executions WHERE run_id = :run"),
                    {"run": run_id},
                )
            ).all()
    finally:
        await engine.dispose()

    assert [str(row.id) for row in rows] == list(outcome.execution_ids)
    assert rows[0].status == "ok"


# --- Corrected — what used to be "repaired" ---


async def test_a_hallucinated_column_is_corrected_on_the_next_iteration(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The path M7 named, now served by the loop rather than a special case."""
    fake_llm.script(_plan("SELECT revenue_total FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(done=False), role="plan", times=1)
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How much revenue?")

    outcome = await _execute(context, run_id)

    assert outcome.state == "answered"
    assert outcome.iterations == 2, "one iteration to be refused, one to succeed"
    assert outcome.stopped_by is None
    assert await _types(context, run_id) == [
        "run_started",
        "context_selected",
        "capability_checked",
        "step_started",
        "plan_created",
        "tool_called",
        "error",
        "sql_rejected",
        "reflection",
        "step_started",
        "plan_created",
        "tool_called",
        "query_executed",
        "result_summarized",
        "reflection",
        # The draft is judged before it becomes the answer (WP9.1).
        "critic_verdict",
        "answer_composed",
        "finding_added",
        "run_finished",
    ]


async def test_the_next_plan_is_told_what_was_refused(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """Feeding the violation back is the whole reason the second attempt works."""
    fake_llm.script(_plan("SELECT revenue_total FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(done=False), role="plan", times=1)
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How much revenue?")

    await _execute(context, run_id)

    second = fake_llm.calls_for("sql")[1].prompt
    assert "refused" in second
    assert "revenue_total" in second


async def test_the_same_statement_is_never_sent_twice(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    """4.4's duplicate rule, end to end."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(done=False), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops?")

    await _execute(context, run_id)

    engine = create_async_engine(wired)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"),
                {"org": str(context.org_id)},
            )
            count = (
                await connection.execute(
                    text("SELECT count(*) FROM query_executions WHERE run_id = :run"),
                    {"run": run_id},
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert count == 1, "the repeat was refused before it was sent"


async def test_a_refusal_that_is_never_corrected_ends_honestly(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """Corrected-or-refused."""
    fake_llm.script(_plan("SELECT revenue_total FROM shops"), role="sql")
    fake_llm.script(_reflect(done=False), role="plan")
    fake_llm.script(_final("I could not answer that.", unanswered="all of it"), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How much revenue?")

    outcome = await _execute(context, run_id)

    assert outcome.status == "completed", "an honest refusal is an ending, not a failure"
    assert outcome.state in {"refused", "partly"}
    assert outcome.execution_ids == ()
    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    # Nothing was concluded about the data, so there is nothing to stand behind.
    assert view.findings == []
    # And the run says so where a screen can read it (B-133).
    assert view.state in {"refused", "partly"}, (
        "a refusal that the API reports as indistinguishable from an answer is a "
        "refusal the screen will label 'answered'"
    )


async def test_a_failure_rewriting_cannot_fix_stops_the_loop(
    context: ToolContext, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rewriting cannot fix a database that is down."""
    from charie.agent.tools import registry as registry_module

    real_call = registry_module.ToolRegistry.call

    async def unreachable(self: object, *args: object, **kwargs: object) -> object:
        from charie.agent.tools.base import ToolResult

        return ToolResult(
            tool="run_sql",
            ok=False,
            error="the database is unreachable",
            code="connection_failed",
            repairable=False,
        )

    monkeypatch.setattr(registry_module.ToolRegistry, "call", unreachable)
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    run_id = await _run_for(context, "How many?")

    outcome = await _execute(context, run_id)

    assert real_call is not None
    assert outcome.state in {"refused", "partly"}
    assert outcome.iterations == 1, "it stopped rather than trying again"
    # One plan call and nothing else: no reflection, no compose.
    assert outcome.llm_calls == 1


async def test_a_run_whose_every_query_failed_refuses_instead_of_describing_the_absence(
    context: ToolContext, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-095, and the owner's decision (D-038)."""
    from charie.agent.tools import registry as registry_module

    async def unreachable(self: object, *args: object, **kwargs: object) -> object:
        from charie.agent.tools.base import ToolResult

        return ToolResult(
            tool="run_sql",
            ok=False,
            error="could not connect to the data source",
            code="engine_error",
            repairable=False,
        )

    monkeypatch.setattr(registry_module.ToolRegistry, "call", unreachable)
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    run_id = await _run_for(context, "How many shops are there?")

    outcome = await _execute(context, run_id)

    assert outcome.status == "completed", "an honest refusal is an ending, not a failure"
    assert outcome.state in {"refused", "partly"}, (
        "nothing reached the database, so nothing was answered"
    )
    assert outcome.llm_calls == 1, "no composing call: there was nothing to compose from"

    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.answer is not None
    assert "could not connect to the data source" in view.answer, (
        "the reader is told what actually failed, in the connector's own words"
    )
    assert any("failed to run" in note for note in view.limitations), (
        "the run knew every query had failed; before B-095 it said nothing"
    )
    assert view.findings == [], "there is no evidence, so there is nothing to stand behind"


# --- Refused before anything ran ---


async def test_a_question_the_catalog_cannot_answer_refuses_without_querying(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    """`answerable=false` is believed on the second telling."""
    fake_llm.script(
        _plan("SELECT 1", answerable=False, reason="There is no revenue column anywhere."),
        role="sql",
    )
    run_id = await _run_for(context, "What was our profit margin?")

    outcome = await _execute(context, run_id)

    assert outcome.state in {"refused", "partly"}
    assert outcome.status == "completed"
    # Two planner calls: the judgement and its one permitted second look (D-055).
    assert outcome.llm_calls == 2
    assert not fake_llm.prompts(role="compose"), "a refusal paid for a composing call"
    assert outcome.iterations == 2
    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.answer == "There is no revenue column anywhere."

    engine = create_async_engine(wired)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"),
                {"org": str(context.org_id)},
            )
            count = (
                await connection.execute(
                    text("SELECT count(*) FROM query_executions WHERE run_id = :run"),
                    {"run": run_id},
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert count == 0, "nothing should have been sent to the customer's database"


# --- Citations, and what is not allowed to be one ---


async def test_a_cited_execution_the_run_never_produced_is_dropped(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """Architecture 4.2: findings may only cite real rows."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("There are 3 shops.", cite=[str(uuid.uuid4())]), role="compose")
    run_id = await _run_for(context, "How many shops?")

    outcome = await _execute(context, run_id)

    assert outcome.execution_ids == ()
    assert "unverifiable_citation" in json.dumps(
        [e.payload for e in await read_events(org_id=context.org_id, run_id=run_id)]
    )
    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.findings == [], "an answer with no verifiable support has no finding"


# --- When the platform breaks ---


async def test_a_provider_failure_fails_the_run_rather_than_refusing_it(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """A refusal says the data could not answer."""
    fake_llm.script(raises=LLMError("the provider is unreachable"), role="sql")
    run_id = await _run_for(context, "How many shops?")

    outcome = await _execute(context, run_id)

    assert outcome.status == "failed"
    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.status == "failed"
    assert view.finished_at is not None, "a failed run must still end"
    assert "error" in await _types(context, run_id)


async def test_a_run_always_ends_even_when_the_agent_crashes(
    context: ToolContext, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `finally`."""
    from charie.agent import runner as runner_module

    async def explode(**kwargs: object) -> object:
        raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(runner_module, "build_context", explode)
    run_id = await _run_for(context, "How many shops?")

    outcome = await _execute(context, run_id)

    assert outcome.status == "failed"
    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.status == "failed"
    assert view.finished_at is not None
    assert (await _types(context, run_id))[-1] == "run_finished"


# --- The checkpoint ---


async def test_the_run_state_is_checkpointed_as_it_goes(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    """Architecture 0.2.4: a redeploy kills in-flight runs."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops?")

    outcome = await _execute(context, run_id)

    engine = create_async_engine(wired)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"),
                {"org": str(context.org_id)},
            )
            state = (
                await connection.execute(
                    text("SELECT state FROM agent_runs WHERE id = :run"), {"run": run_id}
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert state["phase"] == "finished"
    assert [e["execution_id"] for e in state["executions"]] == list(outcome.execution_ids)
    # B-173, on the live path.
    assert state["executions"][0]["rows_shown"] is not None
    assert state["executions"][0]["rows_shown"] <= state["executions"][0]["row_count"]
    assert state["plan"][0]["sql"].startswith("SELECT")
    # Rows are never in the checkpoint — only a summary and the reference (4.4).
    executions = cast(list[dict[str, object]], state["executions"])
    assert all("rows" not in execution for execution in executions)
    for execution in executions:
        for value in execution.values():
            if not isinstance(value, list):
                continue
            nested = cast(list[object], value)
            assert not any(isinstance(item, list) for item in nested), (
                f"a checkpointed execution is carrying something row-shaped: {execution}"
            )

    # And the budget is in its own column, not inside the state (D-023).
    assert "budget" not in state
    engine = create_async_engine(wired)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"),
                {"org": str(context.org_id)},
            )
            spent = (
                await connection.execute(
                    text("SELECT budget FROM agent_runs WHERE id = :run"), {"run": run_id}
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    assert spent["iterations"] == 1
    assert spent["queries"] == 1
    # Read from the default rather than written as a literal (D-068).
    assert spent["limits"]["iterations"] == DEFAULT_ITERATIONS, "the allowance this run was given"


# --- What this run called today (B-005, D-027) ---


async def test_the_trace_records_the_date_relative_periods_were_resolved_against(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """A person reading an answer about "last month" is owed the date that phrase meant."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops did we have last month?")

    await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
        as_of=date(2026, 7, 15),
    )

    events = await read_events(org_id=context.org_id, run_id=run_id)
    selected = next(e for e in events if e.type == "context_selected")
    assert selected.payload["as_of"] == "2026-07-15"


async def test_a_pinned_date_reaches_the_prompt_the_model_is_given(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The mechanism the eval harness depends on."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops did we have last month?")

    await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
        as_of=date(2026, 7, 15),
    )

    planning = fake_llm.calls_for("sql")[0]
    system = " ".join(m.content for m in planning.request.messages if m.role == "system")
    assert "Today is 2026-07-15" in system
    assert "CURRENT_DATE" in system, "the escape is named, not merely the date"


async def test_a_run_with_no_date_given_anchors_on_today(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The default is the wall clock: what a person asking in a browser means."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    await _execute(context, run_id)

    events = await read_events(org_id=context.org_id, run_id=run_id)
    selected = next(e for e in events if e.type == "context_selected")
    assert selected.payload["as_of"] == datetime.now(UTC).date().isoformat()


# --- The critic, wired (WP9.1, architecture M9) ---


async def test_a_wrong_date_range_is_caught_without_asking_a_model(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """M9's acceptance line, end to end, and the half of it that costs nothing."""
    fake_llm.script(
        _plan(
            "SELECT count(*) AS n FROM shops WHERE opened_on >= CAST('2026-06-01' AS DATE) "
            "AND opened_on < CAST('2026-07-01' AS DATE)"
        ),
        role="sql",
        times=1,
    )
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    # The second pass: the loop replans, composes again.
    fake_llm.script(
        _plan(
            "SELECT count(*) AS n FROM shops WHERE opened_on >= CAST('2026-07-01' AS DATE) "
            "AND opened_on < CAST('2026-08-01' AS DATE)"
        ),
        role="sql",
        times=1,
    )
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic", times=1)

    run_id = await _run_for(context, "How many shops opened in July 2026?")
    await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
        as_of=date(2026, 8, 16),
    )

    events = await read_events(org_id=context.org_id, run_id=run_id)
    verdicts = [event for event in events if event.type == "critic_verdict"]
    assert len(verdicts) == 2, "one verdict per composed draft"

    first = verdicts[0].payload
    assert first["verdict"] == "revise"
    assert first["consulted_model"] is False, "arithmetic decided; no model was asked"
    rules = [finding["rule"] for finding in cast("list[dict[str, str]]", first["findings"])]
    assert rules == ["range_matches"]

    # And the proof that the saving is real: exactly one critic call, for the second draft.
    assert len(fake_llm.calls_for("critic")) == 1
    assert len(fake_llm.calls_for("critic")) == 1


async def test_the_re_entry_happens_once_and_only_once(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """Architecture M9 allows one bounded re-entry."""
    for _ in range(2):
        fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
        fake_llm.script(_reflect(), role="plan", times=1)
        fake_llm.script(_cites_the_execution, role="compose", times=1)
        fake_llm.script(
            CriticOut(
                verdict="revise", reasons=["Still overstates the evidence."]
            ).model_dump_json(),
            role="critic",
        )

    run_id = await _run_for(context, "How many shops are there?")
    outcome = await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
    )

    events = await read_events(org_id=context.org_id, run_id=run_id)
    assert len([e for e in events if e.type == "critic_verdict"]) == 2
    assert len(fake_llm.calls_for("critic")) == 2
    assert len(fake_llm.calls_for("compose")) == 2, "two drafts, not three"
    assert outcome.status == "completed", "a rejected second draft is still an ending"


async def test_reentry_keeps_summary_and_outlet_evidence_for_the_final_report(
    context: ToolContext,
    fake_llm: FakeLLM,
) -> None:
    for sql, done in (
        ("SELECT 101 AS company_total FROM shops LIMIT 1", False),
        ("SELECT 202 AS outlet_change FROM regions LIMIT 1", True),
        ("SELECT 303 AS daily_sales FROM products LIMIT 1", True),
    ):
        fake_llm.script(_plan(sql), role="sql", times=1)
        fake_llm.script(_reflect(done=done), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    fake_llm.script(
        CriticOut(verdict="revise", reasons=["Include the daily trend."]).model_dump_json(),
        role="critic",
        times=1,
    )

    def final_report(request: object) -> str:
        prompt = str(getattr(request, "prompt_text", ""))
        # Column names also occur in execution summaries; require the actual result previews.
        preview_ids = re.findall(r"Result of ([0-9a-f-]{36}):", prompt)
        assert len(preview_ids) == 3
        assert all(str(value) in prompt for value in (101, 202, 303))
        return _final("Company total 101; outlet change 202; daily sales 303.", cite=preview_ids)

    fake_llm.script(final_report, role="compose", times=1)
    fake_llm.script(_passes(), role="critic", times=1)
    run_id = await _run_for(context, "Prepare a business review of shops and regions")
    await _execute(context, run_id)

    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.answer == "Company total 101; outlet change 202; daily sales 303."
    assert view.state == "answered"
    assert view.findings[-1].cited
    assert len(view.findings[-1].support) == 3


async def test_the_second_attempt_is_told_what_was_wrong_with_the_first(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The critic's reasons are given to the composer, not hoped for."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    fake_llm.script(
        CriticOut(
            verdict="revise", reasons=["The answer treats a correlation as a cause."]
        ).model_dump_json(),
        role="critic",
    )
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic", times=1)

    run_id = await _run_for(context, "How many shops are there?")
    await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
    )

    second = fake_llm.calls_for("compose")[1]
    prompt = " ".join(m.content for m in second.request.messages)
    assert "A reviewer rejected your previous answer" in prompt
    assert "treats a correlation as a cause" in prompt


async def test_a_run_that_passes_is_criticised_once_and_left_alone(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The common path: one draft, one verdict, no second pass."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic", times=1)

    run_id = await _run_for(context, "How many shops are there?")
    outcome = await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
    )

    events = await read_events(org_id=context.org_id, run_id=run_id)
    verdicts = [e for e in events if e.type == "critic_verdict"]
    assert len(verdicts) == 1
    assert verdicts[0].payload["verdict"] == "pass"
    assert verdicts[0].payload["consulted_model"] is True
    assert len(fake_llm.calls_for("compose")) == 1
    assert outcome.state == "answered"


async def test_the_composer_has_room_for_a_whole_answer(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """B-052, for the composer."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    fake_llm.script(_passes(), role="critic", times=1)

    await _execute(context, await _run_for(context, "How many shops are there?"))

    limits = fake_llm.calls_for("compose")[0].request.limits
    assert limits.max_output_tokens == COMPOSE_OUTPUT_TOKENS
    assert limits.max_output_tokens > 1024


async def test_the_verdict_schema_is_enforced(context: ToolContext, fake_llm: FakeLLM) -> None:
    """A verdict outside the three architecture 4.5 names is not a verdict."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(), role="plan", times=1)
    fake_llm.script(_cites_the_execution, role="compose", times=1)
    fake_llm.script('{"verdict": "looks_fine", "reasons": []}', role="critic", times=1)

    run_id = await _run_for(context, "How many shops are there?")
    outcome = await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
    )

    # The run does not silently accept it.
    assert outcome.status == "failed"


# --- The failure an operator has to be able to read (B-126) ---


async def test_a_deployment_with_no_model_configuration_fails_every_run(
    context: ToolContext, fake_llm: FakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    """The configuration that shipped to dev, driven the way the product does."""
    run_id = await _run_for(context, "How many shops?")

    with caplog.at_level(logging.ERROR, logger="charie.agent.runner"):
        outcome = await execute_run(
            org_id=context.org_id,
            run_id=run_id,
            data_source_id=context.data_source_id or uuid.uuid4(),
            actor_user_id=context.actor_user_id,
            settings=build_settings(llm_models={}),
        )

    assert outcome.status == "failed"

    # The operator's half: the log names the run and the variable to set.
    assert str(run_id) in caplog.text
    assert "LLM_MODELS" in caplog.text

    # The stored half, unchanged: the trace still carries the reason.
    events = await read_events(org_id=context.org_id, run_id=run_id)
    errors = [event for event in events if event.type == "error"]
    assert errors, "a failed run recorded no error event"
    assert "LLM_MODELS" in json.dumps(errors[-1].payload)

    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.status == "failed"
    assert view.finished_at is not None


async def test_an_internal_failure_is_logged_too_and_not_only_the_llm_kind(
    context: ToolContext,
    fake_llm: FakeLLM,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The other call site. Two `except` blocks record a failure and both had to learn to say so."""
    from charie.agent import runner as runner_module

    async def explode(**kwargs: object) -> object:
        raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(runner_module, "research", explode)
    run_id = await _run_for(context, "How many shops?")

    with caplog.at_level(logging.ERROR, logger="charie.agent.runner"):
        outcome = await _execute(context, run_id)

    assert outcome.status == "failed"
    assert str(run_id) in caplog.text
    assert "something nobody predicted" in caplog.text


async def test_a_run_that_succeeds_logs_no_error(
    context: ToolContext, fake_llm: FakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    """The control."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    with caplog.at_level(logging.ERROR, logger="charie.agent.runner"):
        outcome = await _execute(context, run_id)

    assert outcome.status == "completed"
    assert caplog.text == ""


# --- What periods this database can speak about (B-157, D-058) ---


async def _payload_of(context: ToolContext, run_id: uuid.UUID, kind: str) -> dict[str, object]:
    events = await read_events(org_id=context.org_id, run_id=run_id)
    return next(event.payload for event in events if event.type == kind)


async def test_the_measured_period_reaches_the_model_that_writes_the_sql(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """Reached, not merely computed (B-157)."""
    from charie.catalog import profiler

    await profiler.profile(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
    )
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    await _execute(context, run_id)

    payload = await _payload_of(context, run_id, "capability_checked")
    assert payload["available_period"] == "2020-01 to 2024-05"

    planning = " ".join(fake_llm.prompts(role="sql"))
    assert "2020-01 to 2024-05" in planning, (
        "the measured period was computed and never shown to the model that "
        "decides whether a period is missing"
    )
    assert "not a limit on what you may ask" in planning


async def test_an_unprofiled_source_abstains_where_a_reader_can_see_it(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The owner's requirement: a run where the check could not fire must be distinguishable..."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    await _execute(context, run_id)

    payload = await _payload_of(context, run_id, "capability_checked")
    assert "available_period" in payload, "the trace cannot tell an abstention from a pass"
    assert payload["available_period"] is None

    planning = " ".join(fake_llm.prompts(role="sql"))
    assert "not a limit on what you may ask" not in planning, (
        "a range was stated for a source whose columns nobody measured"
    )


async def test_the_answer_records_which_period_it_was_about(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The second half of the check, asserted on what the trace actually carries."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    await _execute(context, run_id)

    payload = await _payload_of(context, run_id, "answer_composed")
    assert "coverage" in payload, "the trace cannot say whether the period was checked"
    coverage = payload["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["status"] == "abstained"
    assert coverage["reason"], "an abstention with no reason is a silence with a label on it"


async def test_an_answer_whose_rows_are_a_period_is_compared_against_the_catalogue(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """B-157's shape, end to end."""
    from charie.catalog import profiler

    await profiler.profile(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
    )
    fake_llm.script(_plan("SELECT opened_on FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "When did the shops open?")

    outcome = await _execute(context, run_id)

    payload = await _payload_of(context, run_id, "answer_composed")
    coverage = payload["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["status"] == "contained", coverage
    assert coverage["answered"] == "2020-01 to 2024-05"
    assert coverage["available"] == "2020-01 to 2024-05"
    assert not any("outside the period" in note for note in outcome.limitations), (
        "an answer inside the catalogue's range was caveated anyway"
    )


async def test_sql_the_engine_rejects_is_corrected_rather_than_giving_up(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The class of failure that ended a live run after one query."""
    # `times=1`, or the first script matches every call and the loop re-proposes the same statement.
    fake_llm.script(
        _plan("SELECT count(*) AS n FROM shops WHERE opened_on > 2021"), role="sql", times=1
    )
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    # The loop reflects after a refusal too, so the first reflection must not end the run.
    fake_llm.script(_reflect(done=False), role="plan", times=1)
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "How many shops are there?")

    outcome = await _execute(context, run_id)

    types = await _types(context, run_id)
    assert types.count("sql_rejected") == 1, (
        f"the engine did not reject the first statement, so this test is not "
        f"exercising the repair path: {types}"
    )
    assert "query_executed" in types, "the corrected attempt never ran"
    assert outcome.state == "answered", (
        f"the run gave up on an error the engine explained how to fix: {outcome.answer}"
    )


# --- A model's judgement is not a platform fact (D-055) ---


async def test_a_judged_refusal_gets_one_more_attempt_before_it_stands(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The second screenshot's failure."""
    fake_llm.script(
        _plan("SELECT 1", answerable=False, reason="no link between waste and revenue"),
        role="sql",
        times=1,
    )
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "can waste be reduced to increase revenue?")

    outcome = await _execute(context, run_id)

    assert outcome.state == "answered", f"the judged refusal was still terminal: {outcome.answer}"
    events = await read_events(org_id=context.org_id, run_id=run_id)
    retried = [e for e in events if e.type == "plan_created" and e.payload.get("retrying")]
    assert len(retried) == 1, "the retry left no trace of itself"
    assert retried[0].payload.get("reason") == "no link between waste and revenue", (
        "the first refusal's reason was not recorded, so nothing can check that the "
        "retried answer still names the gap"
    )


async def test_the_second_attempt_is_asked_something_different(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The property the first version of this test could not see (B-167)."""
    fake_llm.script(
        _plan("SELECT 1", answerable=False, reason="no causal model links waste to revenue"),
        role="sql",
    )
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "can waste be reduced to increase revenue?")

    outcome = await _execute(context, run_id)

    planning = fake_llm.prompts(role="sql")
    assert len(planning) == 2, f"the planner was asked {len(planning)} times, not twice"
    assert planning[0] != planning[1], (
        "the second attempt was given byte-identical input to the first, so the "
        "retry cannot change anything — B-167 exactly"
    )
    assert "no causal model links waste to revenue" in planning[1], (
        "the model's own reason for refusing was not carried into the second ask"
    )
    assert "nearest question" in planning[1], "the instruction that makes a retry worth it"
    # And a model that refuses twice is still believed: this is prompt text, not enforcement.
    assert outcome.state == "refused"


async def test_the_retry_instruction_is_gone_once_a_query_has_run(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """It applies to the attempt that follows the refusal and does not trail through the rest..."""
    fake_llm.script(
        _plan("SELECT 1", answerable=False, reason="cannot be established"), role="sql", times=1
    )
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_plan("SELECT count(*) AS n FROM regions"), role="sql")
    fake_llm.script(_reflect(done=False), role="plan", times=1)
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_cites_the_execution, role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "how many shops are there?")

    await _execute(context, run_id)

    planning = fake_llm.prompts(role="sql")
    assert len(planning) >= 3
    assert "nearest question" in planning[1], "the retry's own attempt lost the instruction"
    assert "nearest question" not in planning[2], (
        "the instruction trailed into an iteration that had already run a query"
    )


async def test_a_judged_refusal_is_retried_once_and_not_twice(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The bound, and the reason it is on the state rather than in a local."""
    fake_llm.script(_plan("SELECT 1", answerable=False, reason="cannot be established"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_passes(), role="critic")
    run_id = await _run_for(context, "can waste be reduced to increase revenue?")

    outcome = await _execute(context, run_id)

    assert outcome.state == "refused", "a model that refuses twice must be believed"
    events = await read_events(org_id=context.org_id, run_id=run_id)
    assert len([e for e in events if e.type == "plan_created" and e.payload.get("retrying")]) == 1
