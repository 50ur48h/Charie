"""Recovery: concurrent starts, empty steps, failure rollback (review fixes).

These run through the real worker (`run_due_jobs`) and real threads — not
through direct `run_step_job` calls — so they prove what production does.
"""

import datetime
import threading

import pytest
from sqlalchemy import text

from charie.learner import runs
from charie.learner.api.learning import run_shape
from charie.learner.job import run_due_jobs
from charie.learner.locks import RunActiveError
from charie.learner.steps.base import STEPS, Step, register_step
from charie.shared.db import session_scope
from charie.shared.jobs.registry import HANDLERS
from charie.shared.knowledge import store, versions
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.learning import Job, LearningRun


@pytest.fixture
def step_world():
    """Three canonical fixture steps; the test drives their behavior."""
    log: list = []
    behavior: dict = {"empty": set(), "fail": set(), "write_entry": set(), "break_txn": set()}
    registered: list[Step] = []

    def make(name: str, title: str) -> None:
        def make_jobs(ctx) -> list:
            if name in behavior["empty"]:
                return []
            return [{"n": 1}]

        def run_job(info, ctx) -> None:
            log.append(("run", name))
            if name in behavior["write_entry"]:
                store.upsert_entry(
                    ctx.session,
                    ctx.version_id,
                    f"metric.{name}",
                    "metric",
                    name.title(),
                    f"Meaning of {name}.",
                    {"tables": []},
                    "guessed",
                    [],
                    "From the worker.",
                )
            if name in behavior["break_txn"]:
                ctx.session.execute(
                    text(
                        "INSERT INTO kb_entries "
                        "(version_id, key, kind, title, meaning, details, confidence, sources) "
                        "VALUES (NULL, 'bogus', 'metric', 't', 'm', '{}', 'guessed', '[]')"
                    )
                )
            if name in behavior["fail"]:
                behavior["fail"].discard(name)
                raise RuntimeError(f"{name} broke")

        def finish(ctx) -> None:
            log.append(("finish", name))

        step = Step(
            name=name,
            title=title,
            job_kind=f"rc_{name}",
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
    yield log, behavior
    for step in registered:
        del STEPS[step.name]
        del HANDLERS[step.job_kind]


def _run(run_id: int) -> LearningRun:
    with session_scope() as session:
        run = session.get(LearningRun, run_id)
        assert run is not None
        session.expunge(run)
        return run


def _job(job_id: int) -> Job:
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        session.expunge(job)
        return job


def _join_all(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), "a worker thread is stuck"


def test_concurrent_starts_create_one_run(db, step_world) -> None:
    barrier = threading.Barrier(2)
    outcomes: list = []

    def attempt(kind: str) -> None:
        with session_scope() as session:
            barrier.wait(timeout=30)
            try:
                run = runs.start_run(session, kind, ["owner_notes", "structure"])
                outcomes.append(("ok", run.id))
            except RunActiveError:
                outcomes.append(("conflict", None))

    threads = [
        threading.Thread(target=attempt, args=("first",)),
        threading.Thread(target=attempt, args=("refresh",)),
    ]
    for thread in threads:
        thread.start()
    _join_all(threads)
    assert sorted(kind for kind, _ in outcomes) == ["conflict", "ok"]
    with session_scope() as session:
        assert session.query(LearningRun).count() == 1
        assert session.query(KbVersion).count() == 1
        run = session.query(LearningRun).one()
        assert run.status == "running"


def test_concurrent_drafts_create_one(db) -> None:
    barrier = threading.Barrier(2)
    ids: list[int] = []

    def attempt() -> None:
        with session_scope() as session:
            barrier.wait(timeout=30)
            ids.append(versions.get_or_create_draft(session, "first_learning").id)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    _join_all(threads)
    assert ids[0] == ids[1]
    with session_scope() as session:
        assert session.query(KbVersion).count() == 1


def test_resume_old_failed_with_newer_active_is_conflict(db, step_world) -> None:
    with session_scope() as session:
        first = runs.start_run(session, "first", ["owner_notes"])
        first_id = first.id
        runs.fail_run(session, first_id, "owner_notes broke.")
    with session_scope() as session:
        refresh = runs.start_run(session, "refresh", ["structure"])
        refresh_id = refresh.id
    with session_scope() as session, pytest.raises(RunActiveError):
        runs.resume_run(session, first_id)
    assert _run(first_id).status == "failed"
    assert _run(refresh_id).status == "running"


def test_empty_step_completes_without_jobs(db, step_world) -> None:
    _log, behavior = step_world
    behavior["empty"].add("owner_notes")
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes"])
        run_id = run.id
    assert run_due_jobs("review") == 0
    finished = _run(run_id)
    assert finished.status == "done"
    assert finished.progress["steps"]["owner_notes"]["total"] == 0
    assert finished.progress["steps"]["owner_notes"]["done"] == 0


def test_empty_middle_step_continues(db, step_world) -> None:
    log, behavior = step_world
    behavior["empty"].add("structure")
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes", "structure", "profile"])
        run_id = run.id
    assert run_due_jobs("review") == 2
    finished = _run(run_id)
    assert finished.status == "done"
    assert finished.step == "profile"
    assert finished.progress["steps"]["structure"]["total"] == 0
    assert finished.progress["steps"]["structure"]["note"] != ""
    assert [entry for entry in log if entry[0] == "finish"] == [
        ("finish", "owner_notes"),
        ("finish", "structure"),
        ("finish", "profile"),
    ]


def test_completed_job_updates_persisted_progress(db, step_world) -> None:
    with session_scope() as session:
        run_id = runs.start_run(session, "first", ["owner_notes"]).id
    assert run_due_jobs("review") == 1
    with session_scope() as session:
        run = session.get(LearningRun, run_id)
        assert run is not None
        shape = run_shape(session, run)
    assert shape["percent"] == 100
    assert shape["progress"][0]["done"] == 1
    assert shape["progress"][0]["total"] == 1


def test_failed_attempt_rolls_back_step_work(db, step_world) -> None:
    _log, behavior = step_world
    behavior["write_entry"].add("owner_notes")
    behavior["fail"].add("owner_notes")
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes"])
        run_id = run.id
        job_id = run.progress["steps"]["owner_notes"]["jobs"][0]
        session.get(Job, job_id).attempts = 2
    assert run_due_jobs("review") == 1
    assert _run(run_id).status == "failed"
    assert _job(job_id).status == "failed"
    with session_scope() as session:
        version_id = session.get(LearningRun, run_id).version_id
        assert store.get_entry(session, version_id, "metric.owner_notes") is None


def test_constrained_failure_settles_run_and_job(db, step_world) -> None:
    _log, behavior = step_world
    behavior["write_entry"].update({"owner_notes", "structure"})
    behavior["break_txn"].add("structure")
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes", "structure"])
        run_id = run.id
    assert run_due_jobs("review") == 2
    assert _run(run_id).status == "running"
    with session_scope() as session:
        job_id = session.get(LearningRun, run_id).progress["steps"]["structure"]["jobs"][0]
        queued = session.get(Job, job_id)
        assert queued.status == "queued"
        queued.attempts = 2
        queued.run_after = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)
    assert run_due_jobs("review") == 1
    finished = _run(run_id)
    assert finished.status == "failed"
    assert _job(job_id).status == "failed"
    with session_scope() as session:
        version_id = session.get(LearningRun, run_id).version_id
        assert store.get_entry(session, version_id, "metric.owner_notes") is not None
        assert store.get_entry(session, version_id, "metric.structure") is None
