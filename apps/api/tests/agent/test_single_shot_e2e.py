"""The whole product, over HTTP, with nothing stubbed but the model."""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from charie.agent import scheduler
from charie.agent.critic import CriticOut
from charie.agent.loop import Reflection
from charie.agent.planner import Plan
from charie.agent.tools.base import ToolContext
from charie.agent.tools.finalize import ChartAsk, FinalizeIn
from charie.auth.jwt_validator import TokenValidator
from charie.auth.principal import Principal
from charie.config import Settings
from charie.llm.base import LLMRequest
from charie.llm.fake import FakeLLM
from charie.main import create_app
from charie.runs import routes as routes_module
from charie.tenancy.session import org_session
from llm_fixture import build_settings

#: One shop opened in 2021 — Northgate, on 2021-02-02 (``tests/customer_db.py``).
SHOPS_OPENED_IN_2021 = 1

QUESTION = "How many shops opened in 2021?"

#: Never connected to — the second source exists only to make the count two.
_THROWAWAY = "not-a-real-credential"

KNOWN_GOOD_SQL = (
    "SELECT count(*) AS shops_opened FROM shops "
    "WHERE opened_on >= '2021-01-01' AND opened_on < '2022-01-01'"
)


class _SubjectAsToken(TokenValidator):
    def __init__(self, user_id: uuid.UUID | None) -> None:
        self._user_id = user_id

    async def validate(self, token: str) -> Principal:
        return Principal(subject=f"sub-{self._user_id}", email="asker@example.com")


def _cite_what_actually_ran(request: LLMRequest) -> str:
    """Compose an answer citing the execution id in this very prompt."""
    prompt = "\n".join(message.content for message in request.messages)
    found = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", prompt)
    assert found is not None, f"the composing prompt carried no execution id:\n{prompt}"
    return FinalizeIn(
        answer=f"{SHOPS_OPENED_IN_2021} shop opened in 2021.",
        supported_by=[found.group(1)],
        confidence="high",
    ).model_dump_json()


def _cite_and_colour(request: LLMRequest) -> str:
    """Compose, and ask for a chart coloured by the column already on the x axis."""
    prompt = "\n".join(message.content for message in request.messages)
    found = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", prompt)
    assert found is not None
    return FinalizeIn(
        answer=f"{SHOPS_OPENED_IN_2021} shop opened in 2021.",
        supported_by=[found.group(1)],
        confidence="high",
        chart=ChartAsk(
            of=found.group(1),
            mark="bar",
            x="shops_opened",
            y="shops_opened",
            series="shops_opened",
        ),
    ).model_dump_json()


def _cite_and_chart(request: LLMRequest) -> str:
    """Compose, and ask for a chart of the result just cited (WP11.1)."""
    prompt = "\n".join(message.content for message in request.messages)
    found = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", prompt)
    assert found is not None
    return FinalizeIn(
        answer=f"{SHOPS_OPENED_IN_2021} shop opened in 2021.",
        supported_by=[found.group(1)],
        confidence="high",
        chart=ChartAsk(of=found.group(1), mark="bar", x="opened_year", y="shops"),
    ).model_dump_json()


@pytest.fixture
def scripted(fake_llm: FakeLLM) -> FakeLLM:
    fake_llm.script(
        Plan(
            sql=KNOWN_GOOD_SQL,
            purpose="Count shops whose opening date falls in 2021",
            answerable=True,
            reason="",
        ).model_dump_json(),
        role="sql",
    )
    # One reflection that ends the investigation: this question needs one query.
    fake_llm.script(
        Reflection(
            findings=[],
            open_questions=[],
            next_purpose="",
            done=True,
            rationale="the count answers it",
        ).model_dump_json(),
        role="plan",
    )
    fake_llm.script(_cite_what_actually_ran, role="compose")
    # A run now ends with a critic pass (WP9.1).
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")
    return fake_llm


async def _ask_over_http(
    context: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], list[object]]:
    """Create a conversation naming the source, ask, and hand back the task."""
    scheduled: list[object] = []
    real_schedule = scheduler.schedule_run

    async def capture(**kwargs: object) -> object:
        task = await real_schedule(**{**kwargs, "settings": build_settings()})  # pyright: ignore[reportArgumentType]
        scheduled.append(task)
        return task

    monkeypatch.setattr(routes_module, "schedule_run", capture)
    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken(context.actor_user_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        headers = {"Authorization": "Bearer asker"}
        created = await client.post(
            f"/v1/orgs/{context.org_id}/conversations",
            headers=headers,
            json={"data_source_id": str(context.data_source_id)},
        )
        assert created.status_code == 201, created.text
        conversation = created.json()
        assert conversation["data_source_id"] == str(context.data_source_id)

        accepted = await client.post(
            f"/v1/orgs/{context.org_id}/conversations/{conversation['id']}/messages",
            headers=headers,
            json={"content": QUESTION, "idempotency_key": uuid.uuid4().hex},
        )
        assert accepted.status_code == 202, accepted.text

    assert scheduled, "the route did not schedule a run"
    return accepted.json(), scheduled


async def _get(context: ToolContext, path: str) -> tuple[int, Any]:
    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken(context.actor_user_id)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(path, headers={"Authorization": "Bearer asker"})
    return response.status_code, response.json()


async def test_a_question_is_answered_over_http_and_the_citation_opens(
    context: ToolContext, scripted: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The M7 criterion, end to end, in the order a user experiences it."""
    accepted, scheduled = await _ask_over_http(context, monkeypatch)
    await scheduled[0]  # pyright: ignore[reportGeneralTypeIssues]
    run_id = accepted["run_id"]

    status, run = await _get(context, f"/v1/orgs/{context.org_id}/runs/{run_id}")
    assert status == 200
    assert run["status"] == "completed"
    assert run["question"] == QUESTION
    assert run["answer"] == f"{SHOPS_OPENED_IN_2021} shop opened in 2021."

    # A finding, carrying the citation.
    assert len(run["findings"]) == 1
    support = run["findings"][0]["support"]
    assert len(support) == 1, "the answer cited nothing, or cited more than it ran"

    # And the citation opens — which is the half B-034 existed to build.
    status, evidence = await _get(
        context, f"/v1/orgs/{context.org_id}/runs/{run_id}/executions/{support[0]}"
    )
    assert status == 200, evidence
    assert evidence["status"] == "ok"
    assert evidence["tables"] == ["public.shops"]
    assert "shops" in evidence["sql"]


async def test_a_chart_that_cannot_be_drawn_says_so_on_the_run(
    context: ToolContext, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property the whole chart design turns on (WP11.1)."""
    fake_llm.script(
        Plan(
            sql=KNOWN_GOOD_SQL,
            purpose="Count shops whose opening date falls in 2021",
            answerable=True,
            reason="",
        ).model_dump_json(),
        role="sql",
    )
    fake_llm.script(
        Reflection(
            findings=[],
            open_questions=[],
            next_purpose="",
            done=True,
            rationale="the count answers it",
        ).model_dump_json(),
        role="plan",
    )
    fake_llm.script(_cite_and_chart, role="compose")
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")

    accepted, scheduled = await _ask_over_http(context, monkeypatch)
    await scheduled[0]  # pyright: ignore[reportGeneralTypeIssues]

    status, run = await _get(context, f"/v1/orgs/{context.org_id}/runs/{accepted['run_id']}")

    assert status == 200
    chart = run["chart"]
    assert chart is not None, "a chart was asked for and the run recorded nothing about it"
    assert chart.get("spec") is None
    # Says what about the result made a picture the wrong answer.
    assert "single figure" in chart["declined"]
    assert chart["code"] == "unchartable_shape"

    # And the limitations are untouched.
    assert not any("chart" in note.lower() for note in run["limitations"])


SERIES_SQL = "SELECT opened_on, name, id FROM shops"


async def test_the_series_the_platform_chose_reaches_the_stored_chart(
    context: ToolContext, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B-109's guard, kept — with the subject changed and the property intact."""
    fake_llm.script(
        Plan(
            sql=SERIES_SQL,
            purpose="List each shop with the date it opened",
            answerable=True,
            reason="",
        ).model_dump_json(),
        role="sql",
    )
    fake_llm.script(
        Reflection(
            findings=[],
            open_questions=[],
            next_purpose="",
            done=True,
            rationale="the rows answer it",
        ).model_dump_json(),
        role="plan",
    )
    fake_llm.script(_cite_and_colour, role="compose")
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")

    accepted, scheduled = await _ask_over_http(context, monkeypatch)
    await scheduled[0]  # pyright: ignore[reportGeneralTypeIssues]

    status, run = await _get(context, f"/v1/orgs/{context.org_id}/runs/{accepted['run_id']}")

    assert status == 200
    chart = run["chart"]
    assert chart is not None, "a chart was asked for and the run recorded nothing about it"
    assert chart.get("declined") is None, chart
    spec = chart["spec"]
    encoding = spec["encoding"]
    assert "color" in encoding, (
        "the series never reached the spec: the channel is unreachable again, which "
        "is the defect B-109 was filed for"
    )
    assert encoding["color"]["field"] == "name"
    # And the platform's own choice of mark travelled with it, rather than the model's.
    assert spec["mark"] == "line"


async def test_the_answer_is_the_database_s_own_number(
    context: ToolContext, scripted: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The DAL really ran, against real rows, and the evidence says so."""
    accepted, scheduled = await _ask_over_http(context, monkeypatch)
    await scheduled[0]  # pyright: ignore[reportGeneralTypeIssues]

    _, run = await _get(context, f"/v1/orgs/{context.org_id}/runs/{accepted['run_id']}")
    citation = run["findings"][0]["support"][0]
    _, evidence = await _get(
        context, f"/v1/orgs/{context.org_id}/runs/{accepted['run_id']}/executions/{citation}"
    )

    assert evidence["row_count"] == 1, "a count returns one row"
    assert evidence["sample_rows"] == [[SHOPS_OPENED_IN_2021]]
    assert evidence["columns"] == ["shops_opened"]
    assert evidence["duration_ms"] is not None, "nothing timed it, so nothing ran it"


async def test_the_whole_path_left_a_record_at_every_step(
    context: ToolContext, scripted: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """message → run → execution → audit, joined up, in one test (plan WP7.3)."""
    accepted, scheduled = await _ask_over_http(context, monkeypatch)
    await scheduled[0]  # pyright: ignore[reportGeneralTypeIssues]
    run_id = uuid.UUID(accepted["run_id"])

    async with org_session(context.org_id) as session:
        message = (
            await session.execute(
                text(
                    "SELECT run_id FROM messages WHERE id = :id AND role = 'user'",
                ),
                {"id": uuid.UUID(accepted["message_id"])},
            )
        ).scalar_one()
        assert message == run_id, "the question does not name the run that answered it"

        answered = (
            await session.execute(
                text("SELECT count(*) FROM messages WHERE run_id = :r AND role = 'assistant'"),
                {"r": run_id},
            )
        ).scalar_one()
        assert answered == 1, "the reply is a message in the conversation, like any other"

        execution_id, sql_hash = (
            await session.execute(
                text(
                    "SELECT id, sql_hash FROM query_executions WHERE run_id = :r AND status = 'ok'"
                ),
                {"r": run_id},
            )
        ).one()

        # The audit row is written in the same transaction as the execution and cannot be...
        action, object_id, details = (
            await session.execute(
                text(
                    "SELECT action, object_id, details FROM audit_log "
                    "WHERE object_id = :o AND action = 'dal.query_executed'"
                ),
                {"o": str(execution_id)},
            )
        ).one()
        assert action == "dal.query_executed"
        assert object_id == str(execution_id)
        assert details["sql_hash"] == sql_hash, "the audit row describes a different statement"

        # And the trace, which is what the user is shown as proof of how the answer was reached.
        traced = {
            row[0]
            for row in (
                await session.execute(
                    text("SELECT type FROM agent_events WHERE run_id = :r"), {"r": run_id}
                )
            ).all()
        }
    assert {"run_started", "query_executed", "answer_composed", "run_finished"} <= traced


async def test_a_conversation_that_names_no_source_refuses_when_there_are_two(
    context: ToolContext, scripted: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal D-022 kept, rather than replaced with a tie-break."""
    assert context.actor_user_id is not None
    from charie.datasources import service as datasources

    await datasources.create_data_source(
        org_id=context.org_id,
        actor_user_id=context.actor_user_id,
        name="Second warehouse",
        engine="pg",
        host="127.0.0.1",
        port=1,
        database="unused",
        username="unused",
        password=_THROWAWAY,
        tls_mode="prefer",
    )

    scheduled: list[object] = []
    real_schedule = scheduler.schedule_run

    async def capture(**kwargs: object) -> object:
        task = await real_schedule(**{**kwargs, "settings": build_settings()})  # pyright: ignore[reportArgumentType]
        scheduled.append(task)
        return task

    monkeypatch.setattr(routes_module, "schedule_run", capture)
    app = create_app(settings=Settings(auth_mode="dev", env="ci", build_env="dev"))
    app.state.token_validator = _SubjectAsToken(context.actor_user_id)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        headers = {"Authorization": "Bearer asker"}
        created = await client.post(
            f"/v1/orgs/{context.org_id}/conversations", headers=headers, json={}
        )
        accepted = await client.post(
            f"/v1/orgs/{context.org_id}/conversations/{created.json()['id']}/messages",
            headers=headers,
            json={"content": QUESTION, "idempotency_key": uuid.uuid4().hex},
        )

    assert accepted.status_code == 202
    await scheduled[0]  # pyright: ignore[reportGeneralTypeIssues]

    _, run = await _get(context, f"/v1/orgs/{context.org_id}/runs/{accepted.json()['run_id']}")
    assert run["status"] == "completed", "a refusal is an ending, not a failure"
    assert "more than one data source" in run["answer"]
    assert "Second warehouse" in run["answer"], "the refusal must name the choices"
    assert run["findings"] == [], "nothing was concluded, so nothing is claimed"
