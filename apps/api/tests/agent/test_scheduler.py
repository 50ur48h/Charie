"""What runs a queued run, and what happens when the process dies under one."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine

from charie.agent import scheduler
from charie.agent.critic import CriticOut
from charie.agent.loop import Reflection
from charie.agent.planner import Plan
from charie.agent.scheduler import (
    INTERRUPTED_REASON,
    AmbiguousDataSourceError,
    resolve_data_source,
    schedule_run,
    sweep_orphaned_runs,
)
from charie.agent.tools.base import ToolContext
from charie.agent.tools.finalize import FinalizeIn
from charie.auth.jwt_validator import TokenValidator
from charie.auth.principal import Principal
from charie.config import Settings
from charie.datasources import service as datasources
from charie.llm.fake import FakeLLM
from charie.main import create_app
from charie.orgs import service as orgs_service
from charie.runs import routes as routes_module
from charie.runs import service as runs
from llm_fixture import build_settings


class _SubjectAsToken(TokenValidator):
    """Resolves every token to one known member of the fixture's organization."""

    def __init__(self, user_id: uuid.UUID | None) -> None:
        self._user_id = user_id

    async def validate(self, token: str) -> Principal:
        return Principal(subject=f"sub-{self._user_id}", email="asker@example.com")


#: Never connected to — this source exists only to make the count two.
_THROWAWAY = "not-a-real-credential"


async def _register_a_second_source(context: ToolContext) -> None:
    assert context.actor_user_id is not None
    await datasources.create_data_source(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        name="Second warehouse",
        engine="pg",
        host="127.0.0.1",
        port=5432,
        database="other",
        username="reader",
        password=_THROWAWAY,
        tls_mode="prefer",
    )


async def _queued(context: ToolContext, question: str = "How many shops?") -> uuid.UUID:
    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)
    asked = await runs.post_message(
        org_id=context.org_id,
        user_id=context.actor_user_id or uuid.uuid4(),
        conversation_id=view.conversation_id,
        content=question,
        idempotency_key=uuid.uuid4().hex,
    )
    return asked.run_id


# --- Choosing a data source ---


async def test_one_registered_source_is_the_one_used(context: ToolContext) -> None:
    resolved = await resolve_data_source(context.org_id)

    assert resolved == context.data_source_id


async def test_two_sources_refuse_and_name_the_choices(context: ToolContext) -> None:
    """No default and no tie-break. Being wrong here is invisible in the answer."""
    await _register_a_second_source(context)

    with pytest.raises(AmbiguousDataSourceError) as raised:
        await resolve_data_source(context.org_id)

    assert "Second warehouse" in str(raised.value)
    assert "Customer" in str(raised.value)
    assert set(raised.value.candidates) == {"Customer", "Second warehouse"}


async def test_no_source_at_all_says_what_to_do_about_it(context: ToolContext) -> None:
    assert context.actor_user_id is not None
    assert context.data_source_id is not None
    await datasources.delete_data_source(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        data_source_id=context.data_source_id,
    )

    with pytest.raises(AmbiguousDataSourceError, match="No data source is registered"):
        await resolve_data_source(context.org_id)


async def test_the_organizations_own_choice_ends_the_ambiguity(context: ToolContext) -> None:
    """An Admin choosing is a person deciding, which is what the refusal demanded."""
    assert context.actor_user_id is not None
    assert context.data_source_id is not None
    await _register_a_second_source(context)

    # Precondition, stated rather than assumed: without a choice this refuses.
    with pytest.raises(AmbiguousDataSourceError):
        await resolve_data_source(context.org_id)

    await orgs_service.set_active_data_source(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        data_source_id=context.data_source_id,
    )

    assert await resolve_data_source(context.org_id) == context.data_source_id


async def test_clearing_the_choice_brings_the_refusal_back(context: ToolContext) -> None:
    """The refusal is kept, not replaced. Un-choosing restores it exactly."""
    assert context.actor_user_id is not None
    assert context.data_source_id is not None
    await _register_a_second_source(context)
    await orgs_service.set_active_data_source(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        data_source_id=context.data_source_id,
    )
    assert await resolve_data_source(context.org_id) == context.data_source_id

    await orgs_service.set_active_data_source(
        org_id=context.org_id, actor_user_id=context.actor_user_id, data_source_id=None
    )

    with pytest.raises(AmbiguousDataSourceError) as raised:
        await resolve_data_source(context.org_id)
    assert set(raised.value.candidates) == {"Customer", "Second warehouse"}


async def test_an_ambiguous_source_ends_the_run_with_an_answer_not_a_silence(
    context: ToolContext,
) -> None:
    """The question was asked, so it gets a reply the person can read."""
    await _register_a_second_source(context)
    run_id = await _queued(context)

    await (await schedule_run(org_id=context.org_id, run_id=run_id))

    view = await runs.get_run(org_id=context.org_id, run_id=run_id)
    assert view.status == "completed"
    assert view.answer is not None
    assert "more than one data source" in view.answer
    assert view.findings == []


# --- Scheduling ---


async def test_a_scheduled_run_is_executed_in_the_background(
    context: ToolContext, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route returns immediately; the run happens after."""
    seen: dict[str, object] = {}

    async def fake_execute(**kwargs: object) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(scheduler, "execute_run", fake_execute)
    run_id = await _queued(context)

    await (await schedule_run(org_id=context.org_id, run_id=run_id, role="reader"))

    assert seen["run_id"] == run_id
    assert seen["org_id"] == context.org_id
    assert seen["data_source_id"] == context.data_source_id


async def test_a_task_that_raises_does_not_escape_into_the_event_loop(
    context: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception out of a background task is logged by asyncio and otherwise invisible."""

    async def explode(**kwargs: object) -> None:
        raise RuntimeError("nobody predicted this")

    monkeypatch.setattr(scheduler, "execute_run", explode)
    run_id = await _queued(context)

    task = await schedule_run(org_id=context.org_id, run_id=run_id)
    await task

    assert task.exception() is None


async def test_the_scheduler_keeps_a_reference_to_the_task(
    context: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """asyncio holds only a weak reference."""

    async def slow(**kwargs: object) -> None:
        return None

    monkeypatch.setattr(scheduler, "execute_run", slow)
    run_id = await _queued(context)

    task = await schedule_run(org_id=context.org_id, run_id=run_id)

    assert task in scheduler.in_flight()
    await task
    assert task not in scheduler.in_flight(), "the done callback should release it"


# --- The orphan sweep ---


async def _status_of(wired: URL, org_id: uuid.UUID, run_id: uuid.UUID) -> tuple[str, str | None]:
    engine = create_async_engine(wired)
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, false)"), {"org": str(org_id)}
            )
            row = (
                await connection.execute(
                    text("SELECT status, failure_reason FROM agent_runs WHERE id = :id"),
                    {"id": run_id},
                )
            ).one()
    finally:
        await engine.dispose()
    return row.status, row.failure_reason


async def test_a_run_left_running_by_a_restart_is_marked_interrupted(
    context: ToolContext, wired: URL
) -> None:
    run_id = await _queued(context)
    await runs.transition(org_id=context.org_id, run_id=run_id, status="running")

    swept = await sweep_orphaned_runs()

    assert swept >= 1
    status, reason = await _status_of(wired, context.org_id, run_id)
    assert status == "interrupted", "a restart is not a failure"
    assert reason == INTERRUPTED_REASON


async def test_the_reason_says_a_restart_happened_rather_than_blaming_the_question(
    context: ToolContext, wired: URL
) -> None:
    """Somebody reading this should not go looking for a bug in their SQL."""
    run_id = await _queued(context)
    await runs.transition(org_id=context.org_id, run_id=run_id, status="running")

    await sweep_orphaned_runs()

    _, reason = await _status_of(wired, context.org_id, run_id)
    assert reason is not None
    assert "restarted" in reason
    assert "Nothing was wrong with the question" in reason


async def test_the_trace_records_the_interruption(context: ToolContext) -> None:
    """`run_finished` with status interrupted and the reason — so the trace, not just the row."""
    from charie.runs.events import read_events

    run_id = await _queued(context)
    await runs.transition(org_id=context.org_id, run_id=run_id, status="running")

    await sweep_orphaned_runs()

    events = await read_events(org_id=context.org_id, run_id=run_id)
    last = events[-1]
    assert last.type == "run_finished"
    assert last.payload["status"] == "interrupted"
    assert "restarted" in str(last.payload["reason"])
    assert last.payload["totals"] == {"interrupted_by": "restart"}


async def test_a_queued_run_is_swept_too(context: ToolContext, wired: URL) -> None:
    """Nothing schedules a queued run except a task inside a process that no longer exists."""
    run_id = await _queued(context)

    await sweep_orphaned_runs()

    status, _ = await _status_of(wired, context.org_id, run_id)
    assert status == "interrupted"


async def test_a_finished_run_is_left_alone(context: ToolContext, wired: URL) -> None:
    """The sweep must not rewrite history. A completed run is a completed run."""
    run_id = await _queued(context)
    await runs.transition(org_id=context.org_id, run_id=run_id, status="running")
    await runs.transition(org_id=context.org_id, run_id=run_id, status="completed")

    await sweep_orphaned_runs()

    status, _ = await _status_of(wired, context.org_id, run_id)
    assert status == "completed"


async def test_the_sweep_reports_nothing_to_do_on_a_clean_start(
    context: ToolContext,
) -> None:
    """Every run in the database already finished, so there is nothing to reconcile."""
    for run_id in (context.run_id, await _queued(context)):
        await runs.transition(org_id=context.org_id, run_id=run_id, status="running")
        await runs.transition(org_id=context.org_id, run_id=run_id, status="completed")

    assert await sweep_orphaned_runs() == 0


# --- Over HTTP ---


async def test_asking_over_http_answers_202_and_the_run_completes_behind_it(
    context: ToolContext, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of WP7.2c, from the client's side."""
    scheduled: list[object] = []
    real_schedule = scheduler.schedule_run

    async def capture(**kwargs: object) -> object:
        # `settings` is injected here because the route has no seam for it.
        task = await real_schedule(**{**kwargs, "settings": build_settings()})  # pyright: ignore[reportArgumentType]
        scheduled.append(task)
        return task

    monkeypatch.setattr(routes_module, "schedule_run", capture)
    fake_llm.script(
        Plan(
            sql="SELECT count(*) AS n FROM shops", purpose="count", answerable=True, reason=""
        ).model_dump_json(),
        role="sql",
    )
    fake_llm.script(
        Reflection(
            findings=[], open_questions=[], next_purpose="", done=True, rationale="answered"
        ).model_dump_json(),
        role="plan",
    )
    fake_llm.script(
        FinalizeIn(
            answer="There are 3 shops.", supported_by=[], confidence="high"
        ).model_dump_json(),
        role="compose",
    )
    # A run now ends with a critic pass (WP9.1).
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")

    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken(context.actor_user_id)
    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"/v1/orgs/{context.org_id}/conversations/{view.conversation_id}/messages",
            headers={"Authorization": "Bearer asker"},
            json={"content": "How many shops?", "idempotency_key": uuid.uuid4().hex},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"

    # The request is already answered; now let the background task finish.
    assert scheduled, "the route did not schedule anything"
    await scheduled[0]  # pyright: ignore[reportGeneralTypeIssues]

    finished = await runs.get_run(org_id=context.org_id, run_id=uuid.UUID(body["run_id"]))
    assert finished.status == "completed"
    assert finished.answer == "There are 3 shops."


async def test_a_replayed_send_does_not_schedule_a_second_run(
    context: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The idempotency key exists to stop a double tap costing twice."""
    scheduled = 0

    async def count(**kwargs: object) -> None:
        nonlocal scheduled
        scheduled += 1

    monkeypatch.setattr(routes_module, "schedule_run", count)
    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken(context.actor_user_id)
    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)
    body = {"content": "How many shops?", "idempotency_key": "one-send"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for _ in range(2):
            response = await client.post(
                f"/v1/orgs/{context.org_id}/conversations/{view.conversation_id}/messages",
                headers={"Authorization": "Bearer asker"},
                json=body,
            )
            assert response.status_code == 202

    assert scheduled == 1
