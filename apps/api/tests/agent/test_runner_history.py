"""A second question in a thread is answered knowing the first (D-029, B-064)."""

from __future__ import annotations

import uuid
from typing import cast

from charie.agent.context import HISTORY_FRAME
from charie.agent.critic import CriticOut
from charie.agent.loop import ReflectFinding, Reflection
from charie.agent.planner import Plan
from charie.agent.runner import execute_run
from charie.agent.tools.base import ToolContext
from charie.agent.tools.finalize import FinalizeIn
from charie.llm.base import Role
from charie.llm.fake import FakeLLM
from charie.runs import service as runs
from charie.runs.events import read_events
from llm_fixture import build_settings


def _plan(sql: str) -> str:
    return Plan(
        sql=sql, purpose="answer the question", answerable=True, reason=""
    ).model_dump_json()


def _reflect() -> str:
    return Reflection(
        findings=[ReflectFinding(statement="counted", supported_by=[], confidence="high")],
        open_questions=[],
        next_purpose="",
        done=True,
        rationale="that answers it",
    ).model_dump_json()


def _final(answer: str) -> str:
    return FinalizeIn(answer=answer, supported_by=[], confidence="high").model_dump_json()


def _passes() -> str:
    return CriticOut(verdict="pass", reasons=[]).model_dump_json()


async def _ask_and_answer(context: ToolContext, question: str, answer: str) -> uuid.UUID:
    """A completed earlier turn, made the way the product makes one."""
    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)
    asked = await runs.post_message(
        org_id=context.org_id,
        user_id=context.actor_user_id or uuid.uuid4(),
        conversation_id=view.conversation_id,
        content=question,
        idempotency_key=uuid.uuid4().hex,
    )
    await runs.transition(org_id=context.org_id, run_id=asked.run_id, status="running")
    await runs.record_answer(org_id=context.org_id, run_id=asked.run_id, content=answer)
    await runs.transition(org_id=context.org_id, run_id=asked.run_id, status="completed")
    return asked.run_id


async def _follow_up(context: ToolContext, question: str) -> uuid.UUID:
    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)
    asked = await runs.post_message(
        org_id=context.org_id,
        user_id=context.actor_user_id or uuid.uuid4(),
        conversation_id=view.conversation_id,
        content=question,
        idempotency_key=uuid.uuid4().hex,
    )
    return asked.run_id


async def _execute(context: ToolContext, run_id: uuid.UUID) -> None:
    await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
    )


def _prompts(fake_llm: FakeLLM, role: str) -> tuple[str, ...]:
    """Exactly the text a real provider would have received, for the one role."""
    return fake_llm.prompts(cast(Role, role))


async def test_the_planner_is_shown_the_question_this_one_follows(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The defect exactly as the owner hit it: a question, then "check again"."""
    await _ask_and_answer(context, "How many shops are there?", "There are 3 shops.")
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("Still 3 shops."), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _follow_up(context, "check again")

    await _execute(context, run_id)

    planning = _prompts(fake_llm, "sql")[0]
    assert "How many shops are there?" in planning
    assert "There are 3 shops." in planning
    assert HISTORY_FRAME in planning


async def test_the_critic_judges_a_follow_up_in_its_thread(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """A critic asked whether a draft answers "check again", with no idea what was being checked."""
    await _ask_and_answer(context, "How many shops are there?", "There are 3 shops.")
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("Still 3 shops."), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _follow_up(context, "check again")

    await _execute(context, run_id)

    assert "How many shops are there?" in _prompts(fake_llm, "critic")[0]


async def test_the_reflection_is_shown_the_thread_too(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """ "Is the question now answered" cannot be judged from "check again" alone."""
    await _ask_and_answer(context, "How many shops are there?", "There are 3 shops.")
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("Still 3 shops."), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _follow_up(context, "check again")

    await _execute(context, run_id)

    assert "How many shops are there?" in _prompts(fake_llm, "plan")[0]


async def test_the_composer_writes_its_answer_knowing_the_thread(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The call that produces the words a person reads."""
    await _ask_and_answer(context, "How many shops are there?", "There are 3 shops.")
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("Still 3 shops."), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _follow_up(context, "check again")

    await _execute(context, run_id)

    assert "How many shops are there?" in _prompts(fake_llm, "compose")[0]


async def test_the_trace_records_how_much_context_the_run_was_given(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """A follow-up answered from a thread is a different act from one answered cold."""
    await _ask_and_answer(context, "How many shops are there?", "There are 3 shops.")
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("Still 3 shops."), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _follow_up(context, "check again")

    await _execute(context, run_id)

    events = await read_events(org_id=context.org_id, run_id=run_id)
    selected = next(event for event in events if event.type == "context_selected")
    assert int(str(selected.payload["history_turns"])) >= 1


async def test_a_follow_up_with_no_nouns_still_finds_the_tables(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """ "check again" names no table, so searching it alone returns nothing and the planner is..."""
    await _ask_and_answer(context, "How many shops are there?", "There are 3 shops.")
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("Still 3 shops."), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _follow_up(context, "check again")

    await _execute(context, run_id)

    events = await read_events(org_id=context.org_id, run_id=run_id)
    selected = next(event for event in events if event.type == "context_selected")
    assert selected.payload["tables"], "a follow-up must not plan against an empty catalog"
    assert selected.payload["tables_found_via"] == "thread"


async def test_a_question_with_words_of_its_own_is_not_pulled_back_to_the_last_one(
    context: ToolContext, fake_llm: FakeLLM
) -> None:
    """The other half of the fallback, and the one that keeps it honest."""
    await _ask_and_answer(context, "How many shops are there?", "There are 3 shops.")
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_final("Counted."), role="compose")
    fake_llm.script(_passes(), role="critic")
    run_id = await _follow_up(context, "how many shops are there now?")

    await _execute(context, run_id)

    events = await read_events(org_id=context.org_id, run_id=run_id)
    selected = next(event for event in events if event.type == "context_selected")
    assert selected.payload["tables_found_via"] == "question"
