"""The agent consulting a document mid-run (B-075, D-032, WP10.2a)."""

from __future__ import annotations

import uuid

from sqlalchemy import URL

from charie.agent.budget import Budget
from charie.agent.critic import CriticOut
from charie.agent.loop import MAX_LOOKUPS, ReflectFinding, Reflection
from charie.agent.planner import Plan
from charie.agent.runner import RunOutcome, execute_run
from charie.agent.tools.base import ToolContext
from charie.agent.tools.finalize import FinalizeIn
from charie.agent.tools.registry import default_registry
from charie.knowledge.ingest import ingest_document
from charie.knowledge.store import LocalDocumentStore
from charie.llm.fake import FakeLLM
from charie.runs import service as runs
from charie.runs.events import read_events
from llm_fixture import build_settings

POLICY = b"""\
# Revenue policy

## Net revenue

Net revenue excludes cancelled and refunded orders. It is the figure reported to
the board every month.
"""

#: A sentence no card contains and no question mentions.
FROM_THE_DOCUMENT = "excludes cancelled and refunded orders"


def _plan(sql: str, *, define: str = "", answerable: bool = True, reason: str = "") -> str:
    return Plan(
        define=define, sql=sql, purpose="counting shops", answerable=answerable, reason=reason
    ).model_dump_json()


def _reflect(*, done: bool, statement: str = "") -> str:
    findings = (
        [ReflectFinding(statement=statement, supported_by=[], confidence="medium")]
        if statement
        else []
    )
    return Reflection(
        findings=findings, open_questions=[], next_purpose="", done=done, rationale="carrying on"
    ).model_dump_json()


def _final() -> str:
    return FinalizeIn(
        answer="Here is what I found.", supported_by=[], confidence="medium"
    ).model_dump_json()


async def _upload(context: ToolContext, store: LocalDocumentStore) -> None:
    """A real document in this organization, ingested the ordinary way."""
    await ingest_document(
        org_id=context.org_id,
        title="Revenue policy",
        payload=POLICY,
        mime="text/markdown",
        store=store,
        settings=build_settings(),
    )


async def _ask(context: ToolContext, question: str) -> uuid.UUID:
    view = await runs.get_run(org_id=context.org_id, run_id=context.run_id)
    asked = await runs.post_message(
        org_id=context.org_id,
        user_id=context.actor_user_id or uuid.uuid4(),
        conversation_id=view.conversation_id,
        content=question,
        idempotency_key=uuid.uuid4().hex,
    )
    return asked.run_id


async def _execute(
    context: ToolContext, run_id: uuid.UUID, budget: Budget | None = None
) -> RunOutcome:
    return await execute_run(
        org_id=context.org_id,
        run_id=run_id,
        data_source_id=context.data_source_id or uuid.uuid4(),
        actor_user_id=context.actor_user_id,
        settings=build_settings(),
        budget=budget,
    )


async def _events(context: ToolContext, run_id: uuid.UUID, kind: str) -> list[dict[str, object]]:
    recorded = await read_events(org_id=context.org_id, run_id=run_id)
    return [dict(event.payload) for event in recorded if event.type == kind]


def _script_lookup_then_answer(fake_llm: FakeLLM, term: str = "net revenue") -> None:
    """Ask what a term means, then write the query knowing it."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops", define=term), role="sql", times=1)
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(done=True, statement="counted the shops"), role="plan", times=1)
    fake_llm.script(_final(), role="compose")
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")


# --- The criterion ---


async def test_the_definition_reaches_the_plan_that_writes_the_sql(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """The gate criterion."""
    await _upload(context, store)
    _script_lookup_then_answer(fake_llm)
    run_id = await _ask(context, "What was net revenue last month?")

    await _execute(context, run_id)

    prompts = fake_llm.prompts(role="sql")
    assert len(prompts) == 2, "the loop did not come back for a second plan"
    assert FROM_THE_DOCUMENT not in prompts[0], "the definition was there before it was looked up"
    assert FROM_THE_DOCUMENT in prompts[1], "the looked-up definition never reached the planner"


async def test_the_trace_shows_the_document_being_consulted(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """The other half of the criterion: a person can see it happened."""
    await _upload(context, store)
    _script_lookup_then_answer(fake_llm)
    run_id = await _ask(context, "What was net revenue last month?")

    await _execute(context, run_id)

    dispatched = await _events(context, run_id, "tool_called")
    assert any(event.get("tool") == "search_knowledge" for event in dispatched)

    consulted = await _events(context, run_id, "knowledge_consulted")
    assert len(consulted) == 1
    assert consulted[0]["term"] == "net revenue"
    assert consulted[0]["passages"], "the trace claims a lookup that found nothing"
    sources = consulted[0]["sources"]
    assert isinstance(sources, list)
    assert any("Revenue policy" in str(source) for source in sources)  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]


async def test_a_lookup_costs_an_iteration_and_no_reflect_call(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """D-032's load-bearing detail. An iteration that looks something up runs no statement."""
    await _upload(context, store)
    _script_lookup_then_answer(fake_llm)
    run_id = await _ask(context, "What was net revenue last month?")

    outcome = await _execute(context, run_id)

    assert outcome.iterations == 2, "the lookup did not consume an iteration"
    assert fake_llm.count(role="sql") == 2
    assert fake_llm.count(role="plan") == 1, "a lookup iteration reflected on nothing"


async def test_a_plan_that_cannot_answer_yet_looks_the_term_up_instead_of_refusing(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """Found by a live run, not by this suite."""
    await _upload(context, store)
    fake_llm.script(
        _plan(
            "SELECT 1 AS placeholder",
            define="net revenue",
            answerable=False,
            reason="the reference data does not define net revenue",
        ),
        role="sql",
        times=1,
    )
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(done=True, statement="counted the shops"), role="plan", times=1)
    fake_llm.script(_final(), role="compose")
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")
    run_id = await _ask(context, "What was net revenue last month?")

    outcome = await _execute(context, run_id)

    assert len(await _events(context, run_id, "knowledge_consulted")) == 1
    assert FROM_THE_DOCUMENT in fake_llm.prompts(role="sql")[1]
    assert outcome.state == "answered", "the run refused instead of asking what the term meant"


async def test_an_unanswerable_plan_with_nothing_to_look_up_still_refuses(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    """The other side of that reordering, which is the one a false block would live in."""
    fake_llm.script(
        _plan("SELECT 1 AS placeholder", answerable=False, reason="no such data here"),
        role="sql",
        times=1,
    )
    fake_llm.script(_final(), role="compose")
    run_id = await _ask(context, "How many unicorns did we sell?")

    outcome = await _execute(context, run_id)

    assert outcome.state != "answered"
    assert await _events(context, run_id, "knowledge_consulted") == []


# --- The ceilings ---


async def test_the_same_term_is_not_looked_up_twice(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """The duplicate-query rule's shape, applied to a second kind of repetition."""
    await _upload(context, store)
    fake_llm.script(
        _plan("SELECT count(*) AS n FROM shops", define="net revenue"), role="sql", times=1
    )
    # Asks for the same thing again. The lookup is refused and the SQL runs.
    fake_llm.script(
        _plan("SELECT count(*) AS n FROM regions", define="net revenue"), role="sql", times=1
    )
    fake_llm.script(_reflect(done=True, statement="counted"), role="plan", times=1)
    fake_llm.script(_final(), role="compose")
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")
    run_id = await _ask(context, "What was net revenue last month?")

    await _execute(context, run_id)

    assert len(await _events(context, run_id, "knowledge_consulted")) == 1
    assert await _events(context, run_id, "query_executed"), (
        "the second step's statement was never run"
    )


async def test_the_next_plan_is_told_what_has_already_been_looked_up(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """Also found live. A refused duplicate is right and silence about it is not."""
    await _upload(context, store)
    _script_lookup_then_answer(fake_llm)
    run_id = await _ask(context, "What was net revenue last month?")

    await _execute(context, run_id)

    second = fake_llm.prompts(role="sql")[1]
    assert "already looked up" in second
    assert "net revenue" in second


async def test_a_run_may_not_look_up_more_than_its_cap(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """`MAX_LOOKUPS` is a ceiling the controller enforces, like every other in this loop."""
    await _upload(context, store)
    for index in range(MAX_LOOKUPS + 1):
        fake_llm.script(
            _plan(f"SELECT count(*) AS n FROM shops WHERE id > {index}", define=f"term {index}"),
            role="sql",
            times=1,
        )
    fake_llm.script(_reflect(done=True, statement="counted"), role="plan", times=1)
    fake_llm.script(_final(), role="compose")
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")
    run_id = await _ask(context, "What was net revenue last month?")

    await _execute(context, run_id)

    assert len(await _events(context, run_id, "knowledge_consulted")) == MAX_LOOKUPS


async def test_a_lookup_that_finds_nothing_does_not_stop_the_run(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    """No document is uploaded at all."""
    _script_lookup_then_answer(fake_llm, term="a term nobody wrote down")
    run_id = await _ask(context, "What was net revenue last month?")

    outcome = await _execute(context, run_id)

    consulted = await _events(context, run_id, "knowledge_consulted")
    assert len(consulted) == 1
    assert consulted[0]["passages"] == 0
    assert "do not infer a definition" in str(consulted[0]["note"])
    assert outcome.status == "completed"
    assert await _events(context, run_id, "query_executed"), (
        "the run stopped instead of going on without a definition"
    )


# --- Prose informs; it does not bind (D-033) ---


async def test_an_answer_resting_on_prose_says_its_definition_was_not_checked(
    context: ToolContext, fake_llm: FakeLLM, wired: URL, store: LocalDocumentStore
) -> None:
    """The owner's principle, made visible to the person reading the answer."""
    await _upload(context, store)
    _script_lookup_then_answer(fake_llm)
    run_id = await _ask(context, "What was net revenue last month?")

    outcome = await _execute(context, run_id)

    assert any("net revenue" in note for note in outcome.limitations), outcome.limitations
    assert any("nothing checked" in note for note in outcome.limitations)


async def test_a_run_that_consulted_nothing_carries_no_such_limitation(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    """The other half, and the one that keeps the first honest."""
    fake_llm.script(_plan("SELECT count(*) AS n FROM shops"), role="sql", times=1)
    fake_llm.script(_reflect(done=True, statement="counted the shops"), role="plan", times=1)
    fake_llm.script(_final(), role="compose")
    fake_llm.script(CriticOut(verdict="pass", reasons=[]).model_dump_json(), role="critic")
    run_id = await _ask(context, "How many shops are there?")

    outcome = await _execute(context, run_id)

    assert not any("read as prose" in note for note in outcome.limitations), outcome.limitations


async def test_a_lookup_that_found_nothing_is_not_caveated_either(
    context: ToolContext, fake_llm: FakeLLM, wired: URL
) -> None:
    """No document is uploaded, so the corpus answers nothing."""
    _script_lookup_then_answer(fake_llm, term="a term nobody wrote down")
    run_id = await _ask(context, "What was net revenue last month?")

    outcome = await _execute(context, run_id)

    assert not any("read as prose" in note for note in outcome.limitations), outcome.limitations


# --- The tool list is honest ---

#: Tools the loop cannot dispatch, each with the reason it is still registered.
NOT_DISPATCHABLE = {
    "search_tables": "the context stage already selects and renders the cards",
    "describe_table": "the context stage already selects and renders the cards",
}

#: What the run can actually dispatch, by name.
DISPATCHABLE = {"run_sql", "search_knowledge", "create_chart_spec"}


def test_every_registered_tool_is_either_dispatchable_or_listed_as_not() -> None:
    """The invariant B-075 is really about."""
    registered = {tool.name for tool in default_registry().available_to("reader")}

    unexplained = registered - DISPATCHABLE - set(NOT_DISPATCHABLE)

    assert unexplained == set(), (
        f"{sorted(unexplained)} is offered to the model and the loop cannot dispatch it. "
        "Wire it into `loop.research`, or add it to NOT_DISPATCHABLE with the reason."
    )
    assert registered >= DISPATCHABLE, "the loop dispatches a tool nobody registered"
