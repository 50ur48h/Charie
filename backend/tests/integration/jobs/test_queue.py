"""The to-do list: take, fail, retry, stuck, pause, resume, cancel."""

import threading
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from charie.shared.db import session_scope
from charie.shared.jobs import queue as jobs
from charie.shared.tables.learning import Job, LearningRun


def _run() -> int:
    with session_scope() as session:
        run = LearningRun(kind="first")
        session.add(run)
        session.flush()
        assert run.id is not None
        return run.id


def _get(job_id: int) -> Job:
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        session.expunge(job)
        return job


def test_take_in_priority_order(db) -> None:
    with session_scope() as session:
        first = jobs.add_job(session, "a", {}, priority=5)
        second = jobs.add_job(session, "b", {}, priority=1)
        third = jobs.add_job(session, "c", {}, priority=3)
    with session_scope() as session:
        assert jobs.take_job(session, "w").id == second
    with session_scope() as session:
        assert jobs.take_job(session, "w").id == third
    with session_scope() as session:
        assert jobs.take_job(session, "w").id == first


def test_future_job_not_taken(db) -> None:
    with session_scope() as session:
        jobs.add_job(session, "a", {}, run_after=datetime.now(UTC) + timedelta(hours=1))
    with session_scope() as session:
        assert jobs.take_job(session, "w") is None


def test_two_workers_never_take_the_same_job(db) -> None:
    with session_scope() as session:
        for _ in range(30):
            jobs.add_job(session, "a", {})
    taken: list[int] = []
    lock = threading.Lock()

    def work() -> None:
        engine = create_engine(db)
        maker = sessionmaker(bind=engine)
        while True:
            with maker() as session:
                job = jobs.take_job(session, "w")
                if job is None:
                    return
                with lock:
                    taken.append(job.id)
                session.commit()
        engine.dispose()

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(taken) == sorted(set(taken)) and len(taken) == 30


def test_fail_retries_then_fails_after_three(db) -> None:
    with session_scope() as session:
        job_id = jobs.add_job(session, "a", {})
    with session_scope() as session:
        jobs.take_job(session, "w")
    with session_scope() as session:
        jobs.fail_job(session, job_id, "boom")
    row = _get(job_id)
    assert row.status == "queued" and row.attempts == 1 and row.error == "boom"
    assert row.run_after > datetime.now(UTC)
    # The retry waits a minute; make it due again and fail the second try.
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "queued"
        job.run_after = datetime.now(UTC)
    with session_scope() as session:
        jobs.take_job(session, "w")
    with session_scope() as session:
        jobs.fail_job(session, job_id, "boom again")
    row = _get(job_id)
    assert row.status == "queued" and row.attempts == 2
    # Third try fails for good.
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "queued"
        job.run_after = datetime.now(UTC)
    with session_scope() as session:
        jobs.take_job(session, "w")
    with session_scope() as session:
        jobs.fail_job(session, job_id, "boom a third time")
    row = _get(job_id)
    assert row.status == "failed" and row.finished_at is not None


def test_stuck_job_goes_back_to_queue(db) -> None:
    with session_scope() as session:
        job_id = jobs.add_job(session, "a", {})
    with session_scope() as session:
        jobs.take_job(session, "w")
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.heartbeat_at = datetime.now(UTC) - timedelta(minutes=6)
    with session_scope() as session:
        assert jobs.requeue_stuck_jobs(session, datetime.now(UTC)) == 1
    row = _get(job_id)
    assert row.status == "queued" and row.attempts == 1 and row.worker is None


def test_stuck_job_after_three_tries_fails(db) -> None:
    with session_scope() as session:
        job_id = jobs.add_job(session, "a", {})
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "running"
        job.attempts = 3
        job.heartbeat_at = datetime.now(UTC) - timedelta(minutes=6)
    with session_scope() as session:
        assert jobs.requeue_stuck_jobs(session, datetime.now(UTC)) == 1
    row = _get(job_id)
    assert row.status == "failed" and row.finished_at is not None
    assert row.error == "It stopped answering 3 times, so Charie gave up on it."


def test_pause_resume_cancel(db) -> None:
    with session_scope() as session:
        run_id = _run()
        ids = [jobs.add_job(session, "a", {}, run_id=run_id) for _ in range(3)]
    with session_scope() as session:
        jobs.take_job(session, "w")
    with session_scope() as session:
        assert jobs.pause_jobs(session, run_id) == 2
    assert sum(1 for i in ids if _get(i).status == "running") == 1
    with session_scope() as session:
        assert jobs.resume_jobs(session, run_id) == 2
    with session_scope() as session:
        assert jobs.cancel_jobs(session, run_id) == 2
    statuses = sorted(_get(i).status for i in ids)
    assert statuses == ["cancelled", "cancelled", "running"]


def test_running_job_not_paused(db) -> None:
    run_id = _run()
    with session_scope() as session:
        job_id = jobs.add_job(session, "a", {}, run_id=run_id)
    with session_scope() as session:
        jobs.take_job(session, "w")
    with session_scope() as session:
        assert jobs.pause_jobs(session, run_id) == 0
    assert _get(job_id).status == "running"
