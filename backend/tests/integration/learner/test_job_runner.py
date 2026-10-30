"""The runner: handlers, errors, pauses, heartbeats, unknown kinds."""

import time

import pytest

from charie.learner import job as runner
from charie.shared.ai.errors import SpendingPaused
from charie.shared.db import session_scope
from charie.shared.jobs.queue import add_job
from charie.shared.jobs.registry import HANDLERS, job_handler
from charie.shared.tables.learning import Job


@pytest.fixture(autouse=True)
def _clean_handlers():
    yield
    for kind in ["test_ok", "test_boom", "test_paused", "test_slow", "test_dup", "test_interrupt"]:
        HANDLERS.pop(kind, None)


def _get(job_id: int) -> Job:
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        session.expunge(job)
        return job


def test_job_runs_from_start_to_end(db) -> None:
    seen: list = []

    @job_handler("test_ok")
    def handle(info) -> None:
        seen.append((info.id, info.payload))

    with session_scope() as session:
        job_id = add_job(session, "test_ok", {"n": 1})
    assert runner.run_due_jobs("w") == 1
    assert seen == [(job_id, {"n": 1})]
    assert _get(job_id).status == "done"


def test_unknown_kind_fails_at_once(db) -> None:
    with session_scope() as session:
        job_id = add_job(session, "nope", {})
    assert runner.run_due_jobs("w") == 1
    row = _get(job_id)
    assert row.status == "failed" and row.attempts == 1
    assert row.error == "No handler for job kind `nope`."


def test_handler_error_saved(db) -> None:
    @job_handler("test_boom")
    def handle(info) -> None:
        raise ValueError("boom\nsecond line")

    with session_scope() as session:
        job_id = add_job(session, "test_boom", {})
    assert runner.run_due_jobs("w") == 1
    row = _get(job_id)
    assert row.error == "boom" and row.status == "queued"


def test_spending_paused_job_is_paused_without_using_a_try(db) -> None:
    @job_handler("test_paused")
    def handle(info) -> None:
        raise SpendingPaused()

    with session_scope() as session:
        job_id = add_job(session, "test_paused", {})
    assert runner.run_due_jobs("w") == 1
    row = _get(job_id)
    assert row.status == "paused" and row.error == "spending_paused"
    assert row.attempts == 0


def test_heartbeat_moves_while_running(db, monkeypatch) -> None:
    monkeypatch.setattr(runner, "HEARTBEAT_SECONDS", 0.05)

    @job_handler("test_slow")
    def handle(info) -> None:
        time.sleep(0.3)

    with session_scope() as session:
        job_id = add_job(session, "test_slow", {})
    assert runner.run_due_jobs("w") == 1
    row = _get(job_id)
    assert row.status == "done" and row.heartbeat_at is not None
    assert row.heartbeat_at > row.locked_at


def test_same_kind_twice_refused() -> None:
    @job_handler("test_dup")
    def first(info) -> None:
        pass

    with pytest.raises(ValueError, match="two handlers"):

        @job_handler("test_dup")
        def second(info) -> None:
            pass


def test_main_without_jobs_says_so(db, capsys) -> None:
    assert runner.main([]) == 0
    assert capsys.readouterr().out == "No jobs are due.\n"


def test_interrupt_requeues_without_using_a_try(db) -> None:
    @job_handler("test_interrupt")
    def handle(info) -> None:
        raise KeyboardInterrupt()

    with session_scope() as session:
        job_id = add_job(session, "test_interrupt", {})
    with pytest.raises(KeyboardInterrupt):
        runner.run_due_jobs("w")
    row = _get(job_id)
    assert row.status == "queued"
    assert row.attempts == 0
    assert row.worker is None and row.locked_at is None and row.heartbeat_at is None
    assert runner._current_job_id is None
