"""Step 1 sorts the owner notes with the AI and writes entries (P07.5)."""

import pytest

from charie.learner.steps import owner_notes
from charie.learner.steps.base import StepContext
from charie.learner.steps.owner_notes import OWNER_NOTES_STEP, finish_step, make_jobs, run_job
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.sources import OwnerNote

NOTES = "Money is always in US dollars. Never use the orders_old table.\n"


def _sort_reply() -> dict:
    return {
        "hard_rules": [
            {
                "title": "Money is always in US dollars",
                "meaning": "Money is always in US dollars.",
                "quote": "Money is always in US dollars.",
                "rule_type": "currency",
                "currency": "USD",
            },
            {
                "title": "Never use the orders_old table",
                "meaning": "Never use the orders_old table.",
                "quote": "Never use the orders_old table.",
                "rule_type": "never_use_table",
                "table": "public.orders_old",
            },
        ],
        "style_rules": [
            {
                "title": "Start with the direct answer",
                "meaning": "Answers start with the direct answer.",
                "quote": "Start with the direct answer.",
                "topics": ["answers"],
            }
        ],
        "data_hints": [
            {
                "title": "Lunch is 11 to 3",
                "meaning": "Lunch is 11 am to 3 pm.",
                "quote": "Lunch is 11 to 3",
                "kind": "default",
            }
        ],
    }


@pytest.fixture
def step_ctx(db_session):
    """A step context on the throwaway database with a fresh draft."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    ctx = StepContext(
        session=db_session,
        run_id=1,
        version_id=version_id,
        source=None,
        connector=None,
        strict_mode=False,
        settings={},
        say=say,
    )
    return ctx, said


def _run(ctx, reply: dict, note_id: int, monkeypatch) -> None:
    """Run the step's job with one queued fake-AI reply."""
    fake = FakeAi().reply("sort_owner_notes", reply)
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(owner_notes, "get_ai", lambda: client)
    info = JobInfo(
        id=1,
        kind="sort_owner_notes",
        payload={"owner_notes_id": note_id, "step": "owner_notes"},
        run_id=ctx.run_id,
        attempts=1,
    )
    run_job(info, ctx)


def _add_notes(session, text: str) -> int:
    note = OwnerNote(text_=text)
    session.add(note)
    session.commit()
    return note.id


def test_sort_makes_rule_style_and_hint_entries(step_ctx, db_session, monkeypatch) -> None:
    ctx, said = step_ctx
    note_id = _add_notes(db_session, NOTES + "Start with the direct answer.\nLunch is 11 to 3.\n")
    assert make_jobs(ctx) == [{"owner_notes_id": note_id}]
    _run(ctx, _sort_reply(), note_id, monkeypatch)
    assert (
        store.get_entry(ctx.session, ctx.version_id, "rule.currency.money_is_always_in_us_dollars")
        is not None
    )
    style = store.get_entry(ctx.session, ctx.version_id, "style.start_with_the_direct_answer")
    assert style is not None and style.confidence == "confirmed"
    hint = store.get_entry(ctx.session, ctx.version_id, "default.notes.lunch_is_11_to_3")
    assert hint is not None
    assert [message for kind, message in said if kind == "found"] == [
        "Hard rule: Money is always in US dollars.",
        "Hard rule: Never use the orders_old table.",
        "Sorted your notes: 2 hard rules, 1 style rule and 1 hint.",
    ]
    assert db_session.get(OwnerNote, note_id).sorted_at is not None


def test_made_up_quote_is_dropped(step_ctx, db_session, monkeypatch) -> None:
    ctx, said = step_ctx
    note_id = _add_notes(db_session, NOTES + "Start with the direct answer.\nLunch is 11 to 3.\n")
    reply = _sort_reply()
    reply["hard_rules"].append(
        {
            "title": "Invented rule",
            "meaning": "Made up.",
            "quote": "Never said anywhere.",
            "rule_type": "currency",
            "currency": "EUR",
        }
    )
    _run(ctx, reply, note_id, monkeypatch)
    assert store.get_entry(ctx.session, ctx.version_id, "rule.currency.invented_rule") is None
    assert (
        "warning",
        "I left out “Invented rule”: its words aren't in your notes.",
    ) in said


def test_new_number_falls_back_to_quote(step_ctx, db_session, monkeypatch) -> None:
    ctx, _ = step_ctx
    note_id = _add_notes(db_session, NOTES + "Start with the direct answer.\nLunch is 11 to 3.\n")
    reply = _sort_reply()
    reply["data_hints"][0]["meaning"] = "Lunch is 11 am to 5 pm."
    _run(ctx, reply, note_id, monkeypatch)
    hint = store.get_entry(ctx.session, ctx.version_id, "default.notes.lunch_is_11_to_3")
    assert hint is not None
    assert hint.meaning == "Lunch is 11 to 3"


def test_no_notes_skips_the_step(step_ctx) -> None:
    ctx, _ = step_ctx
    assert make_jobs(ctx) == []
    assert OWNER_NOTES_STEP.empty_note == "You haven't added notes yet, so I skipped this step."


def test_resort_removes_old_note_entries(step_ctx, db_session, monkeypatch) -> None:
    ctx, _ = step_ctx
    first_id = _add_notes(db_session, NOTES + "Start with the direct answer.\nLunch is 11 to 3.\n")
    _run(ctx, _sort_reply(), first_id, monkeypatch)
    assert (
        store.get_entry(ctx.session, ctx.version_id, "style.start_with_the_direct_answer")
        is not None
    )
    second_id = _add_notes(db_session, NOTES + "Start with the direct answer.\nLunch is 11 to 3.\n")
    reply = _sort_reply()
    reply["style_rules"] = []
    _run(ctx, reply, second_id, monkeypatch)
    assert (
        store.get_entry(ctx.session, ctx.version_id, "style.start_with_the_direct_answer") is None
    )
    assert (
        store.get_entry(ctx.session, ctx.version_id, "rule.currency.money_is_always_in_us_dollars")
        is not None
    )


def test_finish_counts_the_sort(step_ctx, db_session, monkeypatch) -> None:
    ctx, said = step_ctx
    note_id = _add_notes(db_session, NOTES + "Start with the direct answer.\nLunch is 11 to 3.\n")
    reply = _sort_reply()
    reply["style_rules"] = []
    reply["data_hints"] = []
    _run(ctx, reply, note_id, monkeypatch)
    finish_step(ctx)
    assert said[-1] == ("found", "2 hard rules, 0 style rules and 0 hints.")
