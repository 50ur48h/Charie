"""The third state, derived — and proof that it travels (B-134, D-044)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from charie.agent.composer import RUN_STATES, run_state
from charie.agent.runner import execute_run
from charie.agent.tools.base import ToolContext
from charie.agent.tools.finalize import FinalizeIn
from charie.db.models import RUN_OUTCOME_STATES
from charie.llm.fake import FakeLLM
from charie.runs import service as runs
from charie.runs.routes import run_out

MIGRATION = (
    Path(__file__).resolve().parents[2] / "src/charie/db/alembic/versions/0030_run_outcome_state.py"
)


def _draft(*, unanswered: str = "") -> FinalizeIn:
    return FinalizeIn(answer="Outlet C, 3.398 kg.", unanswered=unanswered, confidence="high")


# --- The derivation ---


def test_a_named_gap_with_nothing_behind_it_is_a_refusal() -> None:
    """The run named what it could not answer and cited nothing, so it stands behind nothing."""
    assert run_state(_draft(unanswered="the cost"), ()) == "refused"


def test_naming_no_gap_is_answered_even_without_citations() -> None:
    """The rule this started with was wrong here, and three tests said so."""
    assert run_state(_draft(), ()) == "answered"


def test_a_citation_and_a_named_gap_is_partial() -> None:
    """The case that did not exist before D-044."""
    assert run_state(_draft(unanswered="the cost"), ("exec-1",)) == "partly"


def test_a_citation_and_no_named_gap_is_answered() -> None:
    """The control."""
    assert run_state(_draft(), ("exec-1",)) == "answered"


def test_whitespace_is_not_a_named_gap() -> None:
    """A model that emits `" "` must not put the run into a state whose whole promise is that..."""
    assert run_state(_draft(unanswered="   "), ("exec-1",)) == "answered"


def test_the_states_match_everywhere_they_are_written() -> None:
    """Three lists in two languages, so something has to count them."""
    declared = re.search(r"OUTCOME_STATES = \(([^)]*)\)", MIGRATION.read_text(encoding="utf-8"))
    assert declared, "OUTCOME_STATES not found in revision 0030"
    in_migration = tuple(re.findall(r'"([a-z]+)"', declared.group(1)))

    assert in_migration == RUN_STATES
    assert RUN_OUTCOME_STATES == RUN_STATES


# --- The hops ---


def _plan_shops(sql: str = "SELECT count(*) AS n FROM shops") -> str:
    from charie.agent.planner import Plan

    return Plan(
        sql=sql, purpose="answer the question", answerable=True, reason=""
    ).model_dump_json()


def _reflect() -> str:
    from charie.agent.loop import Reflection

    return Reflection(
        findings=[], open_questions=[], next_purpose="", done=True, rationale="that answers it"
    ).model_dump_json()


def _passes() -> str:
    from charie.agent.critic import CriticOut

    return CriticOut(verdict="pass", reasons=[]).model_dump_json()


async def test_a_partial_answer_survives_every_hop(context: ToolContext, fake_llm: FakeLLM) -> None:
    """The reachability proof, and the reason this PR is not just a migration."""
    from llm_fixture import build_settings

    def _compose_naming_the_gap(request: object) -> str:
        """Cite by reading the execution id out of the prompt, as `test_runner` does."""
        found = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            str(getattr(request, "prompt_text", "")),
        )
        assert found is not None, "the composing prompt named no execution"
        return FinalizeIn(
            answer="Outlet C wastes the most, 3.398 kg. Its cost is not recorded.",
            unanswered="the cost",
            supported_by=[found.group(0)],
            confidence="high",
        ).model_dump_json()

    fake_llm.script(_plan_shops(), role="sql")
    fake_llm.script(_reflect(), role="plan")
    fake_llm.script(_compose_naming_the_gap, role="compose")
    fake_llm.script(_passes(), role="critic")

    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)
    asked = await runs.post_message(
        org_id=context.org_id,
        user_id=context.actor_user_id or uuid.uuid4(),
        conversation_id=view.conversation_id,
        content="which outlet wastes the most, and what does it cost?",
        idempotency_key=uuid.uuid4().hex,
    )
    await execute_run(
        org_id=context.org_id,
        run_id=asked.run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
    )

    stored = await runs.get_run(org_id=context.org_id, run_id=asked.run_id)
    body = run_out(stored).model_dump()

    assert body["unanswered"] == "the cost", (
        "the composer named what it could not answer and the API did not carry it — "
        "which is B-109's shape and the whole reason this test exists"
    )
    assert body["state"] == "partly"
