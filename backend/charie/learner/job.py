"""The learner job: run the due to-do jobs, then exit (`--watch` keeps checking)."""

import argparse
import os
import socket
import sys
import threading
import time
from datetime import UTC, datetime

from charie.shared.ai.errors import SpendingPaused
from charie.shared.db import session_scope
from charie.shared.jobs.queue import (
    fail_job,
    finish_job,
    requeue_stuck_jobs,
    take_job,
)
from charie.shared.jobs.registry import HANDLERS, JobInfo
from charie.shared.tables.learning import Job

from charie.learner.steps import owner_notes  # noqa: F401 (registers the step)

HEARTBEAT_SECONDS = 30
WATCH_SECONDS = 5

_current_job_id: int | None = None


def worker_name() -> str:
    """`<host name>-<process id>`, so two workers never share a job."""
    return f"{socket.gethostname()}-{os.getpid()}"


def _beat(job_id: int, stop: threading.Event) -> None:
    """Refresh the heartbeat on its own session until the handler returns."""
    from charie.shared.jobs.queue import heartbeat

    while not stop.wait(HEARTBEAT_SECONDS):
        with session_scope() as session:
            heartbeat(session, job_id)


def _park_job(session, job_id: int) -> None:
    """Put a running job back to waiting; the interrupted try doesn't count."""
    job = session.get(Job, job_id)
    if job is not None and job.status == "running":
        job.status = "queued"
        job.attempts = max(0, job.attempts - 1)
        job.locked_at = None
        job.heartbeat_at = None
        job.worker = None


def _park_current_job() -> None:
    """Ctrl+C between jobs puts the running job back to waiting."""
    global _current_job_id
    if _current_job_id is None:
        return
    with session_scope() as session:
        _park_job(session, _current_job_id)
    _current_job_id = None


def _unpause_mark(session, job_id: int) -> None:
    """Spending paused the job; the try it took doesn't count."""
    job = session.get(Job, job_id)
    if job is not None:
        job.status = "paused"
        job.error = "spending_paused"
        job.attempts = max(0, job.attempts - 1)
        job.locked_at = None
        job.heartbeat_at = None
        job.worker = None


def run_due_jobs(worker: str) -> int:
    """Run every due job one after another; returns how many ran."""
    global _current_job_id
    done = 0
    while True:
        with session_scope() as session:
            requeue_stuck_jobs(session, datetime.now(UTC))
            job = take_job(session, worker)
            if job is None:
                return done
            info = JobInfo(
                id=job.id,
                kind=job.kind,
                payload=dict(job.payload),
                run_id=job.run_id,
                attempts=job.attempts,
            )
        handler = HANDLERS.get(info.kind)
        if handler is None:
            with session_scope() as session:
                job_row = session.get(Job, info.id)
                if job_row is not None:
                    job_row.error = f"No handler for job kind `{info.kind}`."
                finish_job(session, info.id, "failed")
            done += 1
            continue
        _current_job_id = info.id
        stop = threading.Event()
        beater = threading.Thread(target=_beat, args=(info.id, stop), daemon=True)
        try:
            beater.start()
            handler(info)
        except KeyboardInterrupt:
            with session_scope() as session:
                _park_job(session, info.id)
            raise
        except SpendingPaused:
            with session_scope() as session:
                _unpause_mark(session, info.id)
        except Exception as err:
            with session_scope() as session:
                fail_job(session, info.id, str(err).split("\n")[0])
        else:
            with session_scope() as session:
                finish_job(session, info.id, "done")
        finally:
            stop.set()
            _current_job_id = None
        done += 1


def main(argv: list[str] | None = None) -> int:
    """Without `--watch` run due jobs and exit; with it, keep checking."""
    parser = argparse.ArgumentParser(prog="charie.learner.job")
    parser.add_argument("--watch", action="store_true", help="keep checking every 5 seconds")
    watch = parser.parse_args(argv if argv is not None else sys.argv[1:]).watch
    worker = worker_name()
    if not watch:
        count = run_due_jobs(worker)
        print(f"Ran {count} jobs." if count else "No jobs are due.")
        return 0
    print("Watching the to-do list. Press Ctrl+C to stop.")
    try:
        while True:
            run_due_jobs(worker)
            time.sleep(WATCH_SECONDS)
    except KeyboardInterrupt:
        _park_current_job()
        print("Stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
