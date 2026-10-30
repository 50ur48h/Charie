"""Learning runs: start once, dispatch, retry, pause, resume (P07.1)."""

import pytest

from charie.learner import runs
from charie.learner.runs import RunActiveError
from charie.learner.steps.base import STEPS, Step, register_step
from charie.shared.db import session_scope
from charie.shared.jobs.registry import HANDLERS, JobInfo
from charie.shared.tables.learning import LearningEvent, LearningRun


@pytest.fixture
def three_steps():
    """Three canonical fixture steps that record their calls; unregistered after."""
    log: list = []
    fail: set[str] = set()
    spend: set[str] = set()
    registered: list[Step] = []

    def make(name: str, title: str) -> None:
        def make_jobs(ctx) -> list:
            return [{"n": 1}]

        def run_job(info, ctx) -> None:
            from charie.shared.ai.errors import SpendingPaused

            log.append(("run", name))
            if name in spend:
                raise SpendingPaused()
            if name in fail:
                fail.discard(name)
                raise RuntimeError(f"{name} broke once")

        def finish(ctx) -> None:
            log.append(("finish", name))

        step = Step(
            name=name,
            title=title,
            job_kind=f"test_{name}",
            make_jobs=make_jobs,
            run_job=run_job,
            finish=finish,
        )
        register_step(step)
        runs.register_step_handler(name)
        registered.append(step)

    for step_name, title in [
        ("owner_notes", "Read your notes"),
        ("structure", "Study the database structure"),
        ("profile", "Look at the data itself"),
    ]:
        make(step_name, title)
    yield log, fail, spend
    for step in registered:
        del STEPS[step.name]
        del HANDLERS[step.job_kind]


def _run(run_id: int) -> LearningRun:
    with session_scope() as session:
        run = session.get(LearningRun, run_id)
        assert run is not None
        session.expunge(run)
        return run


def _events(run_id: int) -> list[str]:
    with session_scope() as session:
        rows = (
            session.query(LearningEvent)
            .filter(LearningEvent.run_id == run_id)
            .order_by(LearningEvent.id)
            .all()
        )
        return [row.message for row in rows]


def _first_job(run_id: int, step: str) -> JobInfo:
    """The prepared job of the run's current step."""
    with session_scope() as session:
        run = session.get(LearningRun, run_id)
        assert run is not None
        job_id = run.progress["steps"][step]["jobs"][0]
    return JobInfo(id=job_id, kind=f"test_{step}", payload={"n": 1, "step": step}, run_id=run_id)


def test_concurrent_start(db, three_steps) -> None:
    with session_scope() as session:
        first = runs.start_run(session, "first", ["owner_notes", "structure"])
        run_id = first.id
        assert first.version_id is not None
        with pytest.raises(RunActiveError):
            runs.start_run(session, "refresh", ["profile"])
    with session_scope() as session:
        assert session.query(LearningRun).count() == 1
    assert _run(run_id).version_id is not None


def test_start_while_paused(db, three_steps) -> None:
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes"])
        assert runs.pause_run(session, run.id, "user") is True
    with session_scope() as session, pytest.raises(RunActiveError):
        runs.start_run(session, "refresh", ["structure"])


def test_register_step_twice_refused(db, three_steps) -> None:
    step = Step(
        name="owner_notes",
        title="Read your notes",
        job_kind="test_owner_notes",
        make_jobs=lambda ctx: [],
        run_job=lambda info, ctx: None,
    )
    with pytest.raises(ValueError, match="already registered"):
        register_step(step)


def test_three_steps(db, three_steps) -> None:
    log, _fail, _spend = three_steps
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes", "structure", "profile"])
        run_id = run.id
    for name in ("owner_notes", "structure", "profile"):
        runs.run_step_job(_first_job(run_id, name))
    assert [entry for entry in log if entry[0] == "run"] == [
        ("run", "owner_notes"),
        ("run", "structure"),
        ("run", "profile"),
    ]
    assert [entry for entry in log if entry[0] == "finish"] == [
        ("finish", "owner_notes"),
        ("finish", "structure"),
        ("finish", "profile"),
    ]
    assert _run(run_id).status == "done"
    assert sum("All done in" in message for message in _events(run_id)) == 1


def test_retry_idempotent(db, three_steps) -> None:
    log, fail, _spend = three_steps
    fail.add("structure")
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes", "structure"])
        run_id = run.id
    runs.run_step_job(_first_job(run_id, "owner_notes"))
    with pytest.raises(RuntimeError, match="structure broke once"):
        runs.run_step_job(_first_job(run_id, "structure"))
    runs.run_step_job(_first_job(run_id, "structure"))
    assert log.count(("run", "structure")) == 2
    assert log.count(("finish", "structure")) == 1
    with session_scope() as session:
        run = session.get(LearningRun, run_id)
        assert run is not None
        assert len(run.progress["steps"]["structure"]["jobs"]) == 1
    assert sum("Step 2 of 2" in message for message in _events(run_id)) == 1


def test_fail_run_after_three_tries(db, three_steps) -> None:
    log, fail, _spend = three_steps
    fail.add("owner_notes")
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes"])
        run_id = run.id
    info = _first_job(run_id, "owner_notes")
    failing = JobInfo(id=info.id, kind=info.kind, payload=info.payload, run_id=run_id, attempts=3)
    with pytest.raises(RuntimeError, match="owner_notes broke once"):
        runs.run_step_job(failing)
    assert _run(run_id).status == "failed"


def test_pause_resume(db, three_steps) -> None:
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes", "structure"])
        run_id = run.id
        assert runs.pause_run(session, run_id, "user") is True
        assert runs.pause_run(session, run_id, "user") is False
    assert _run(run_id).status == "paused"
    assert sum("paused" in message for message in _events(run_id)) == 1
    with session_scope() as session:
        assert runs.resume_run(session, run_id) is True
    assert _run(run_id).status == "running"
    assert _run(run_id).paused_by is None


def test_budget_raise_preserves_user_pause(db, three_steps, monkeypatch) -> None:
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes"])
        run_id = run.id
        assert runs.pause_run(session, run_id, "user") is True
    with session_scope() as session:
        assert runs.resume_after_spending_raise(session, run_id) is False
    assert _run(run_id).status == "paused"
    monkeypatch.setattr(runs, "_spending_ok", lambda session: False)
    with session_scope() as session:
        assert runs.pause_run(session, run_id, "user") is False
    with session_scope() as session:
        run = session.get(LearningRun, run_id)
        assert run is not None
        run.paused_by = "spending"
        session.commit()
    with session_scope() as session:
        assert runs.resume_after_spending_raise(session, run_id) is False
    assert _run(run_id).status == "paused"


def test_running_job_finishes_while_paused(db, three_steps) -> None:
    log, _fail, _spend = three_steps
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes", "structure"])
        run_id = run.id
        assert runs.pause_run(session, run_id, "user") is True
    runs.run_step_job(_first_job(run_id, "owner_notes"))
    assert ("finish", "owner_notes") in log
    assert _run(run_id).status == "paused"
    assert _run(run_id).step == "owner_notes"
    with session_scope() as session:
        assert runs.resume_run(session, run_id) is True
    assert _run(run_id).step == "structure"


def test_start_with_no_steps_finishes(db) -> None:
    with session_scope() as session:
        run = runs.start_run(session, "first", [])
        run_id = run.id
        assert run.status == "done"
        assert run.step is None
    assert _events(run_id) == ["All done in 1 second."]


def test_pause_spending_and_budget_resume(db, three_steps) -> None:
    log, _fail, spend = three_steps
    spend.add("owner_notes")
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes"])
        run_id = run.id
    from charie.shared.ai.errors import SpendingPaused

    with pytest.raises(SpendingPaused):
        runs.run_step_job(_first_job(run_id, "owner_notes"))
    paused = _run(run_id)
    assert paused.status == "paused"
    assert paused.paused_by == "spending"
    with session_scope() as session:
        assert runs.resume_after_spending_raise(session, run_id) is True
    assert _run(run_id).status == "running"
