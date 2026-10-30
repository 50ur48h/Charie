"""The live feed: replay, order, no duplicate completion (P07.1)."""

import pytest

from charie.learner import runs
from charie.learner.events import add_event, feed_lines
from charie.learner.steps.base import STEPS, Step, register_step
from charie.shared.db import session_scope
from charie.shared.jobs.registry import HANDLERS, JobInfo
from charie.shared.tables.learning import LearningEvent, LearningRun


@pytest.fixture
def one_step():
    """One canonical fixture step; unregistered after."""
    registered: list = []

    def make_jobs(ctx) -> list:
        return [{"n": 1}]

    def run_job(info, ctx) -> None:
        return None

    step = Step(
        name="owner_notes",
        title="Read your notes",
        job_kind="test_owner_notes",
        make_jobs=make_jobs,
        run_job=run_job,
    )
    register_step(step)
    runs.register_step_handler("owner_notes")
    registered.append(step)
    yield
    for item in registered:
        del STEPS[item.name]
        del HANDLERS[item.job_kind]


def _start() -> int:
    with session_scope() as session:
        return runs.start_run(session, "first", ["owner_notes"]).id


def _done_messages(run_id: int) -> list[str]:
    with session_scope() as session:
        rows = (
            session.query(LearningEvent)
            .filter(LearningEvent.run_id == run_id, LearningEvent.kind == "done")
            .order_by(LearningEvent.id)
            .all()
        )
        return [row.message for row in rows]


def test_replay_after_restart(db, one_step) -> None:
    run_id = _start()
    with session_scope() as session:
        add_event(session, run_id, "found", "Found 3 tables.")
        add_event(session, run_id, "info", "Still looking.")
    first = list(feed_lines(session_scope, run_id, 0, limit=10))
    assert len(first) == 5
    assert "Found 3 tables." in "\n".join(first)
    second = list(feed_lines(session_scope, run_id, 3, limit=10))
    assert "Found 3 tables." not in "\n".join(second)
    assert "Still looking." not in "\n".join(second)


def test_event_order(db, one_step) -> None:
    run_id = _start()
    with session_scope() as session:
        add_event(session, run_id, "info", "First.")
        add_event(session, run_id, "found", "Second.")
        add_event(session, run_id, "info", "Third.")
    lines = list(feed_lines(session_scope, run_id, 1, limit=3))
    assert [block.splitlines()[0] for block in lines] == ["id: 2", "id: 3", "id: 4"]
    assert "First." in lines[0] and "Second." in lines[1] and "Third." in lines[2]


def test_no_duplicate_completion(db, one_step) -> None:
    run_id = _start()
    with session_scope() as session:
        run = session.get(LearningRun, run_id)
        assert run is not None
        job_id = run.progress["steps"]["owner_notes"]["jobs"][0]
    runs.run_step_job(
        JobInfo(
            id=job_id,
            kind="test_owner_notes",
            payload={"n": 1, "step": "owner_notes"},
            run_id=run_id,
        )
    )
    with session_scope() as session:
        runs.advance_run(session, run_id)
        runs.advance_run(session, run_id)
    assert _done_messages(run_id) == ["All done in 1 second."]
