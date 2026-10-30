"""The queue: add, take, finish, fail, pause, resume, cancel, requeue stuck."""

import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.tables.learning import Job

STUCK_AFTER = datetime.timedelta(minutes=5)
GAVE_UP = "It stopped answering 3 times, so Charie gave up on it."


def add_job(
    session: Session,
    kind: str,
    payload: dict[str, Any],
    *,
    run_id: int | None = None,
    priority: int = 100,
    run_after: datetime.datetime | None = None,
) -> int:
    """Queue one job; returns its id."""
    job = Job(kind=kind, payload=payload, run_id=run_id, priority=priority)
    if run_after is not None:
        job.run_after = run_after
    session.add(job)
    session.flush()
    return job.id


def take_job(session: Session, worker: str) -> Job | None:
    """Take the oldest due job (05's claim query); two workers never share one."""
    job = session.scalar(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= func.now())
        .order_by(Job.priority, Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.locked_at = func.now()
    job.heartbeat_at = func.now()
    job.worker = worker
    job.attempts = job.attempts + 1
    session.flush()
    return job


def heartbeat(session: Session, job_id: int) -> None:
    """The handler is still alive; push the stuck deadline out."""
    job = session.get(Job, job_id)
    if job is not None:
        job.heartbeat_at = func.now()
        session.flush()


def finish_job(session: Session, job_id: int, status: str) -> None:
    """Mark the job `done` (or `failed`); handlers save their own work first."""
    job = session.get(Job, job_id)
    if job is not None:
        job.status = status
        job.finished_at = func.now()
        session.flush()


def fail_job(session: Session, job_id: int, error: str) -> None:
    """Retry (at most 3 tries) or fail; the wait grows one minute per try."""
    job = session.get(Job, job_id)
    if job is None:
        return
    job.error = error
    if job.attempts < 3:
        job.status = "queued"
        job.locked_at = None
        job.heartbeat_at = None
        job.worker = None
        job.run_after = func.now() + datetime.timedelta(minutes=job.attempts)
    else:
        job.status = "failed"
        job.finished_at = func.now()
    session.flush()


def _move_jobs(session: Session, run_id: int, from_statuses: tuple[str, ...], to: str) -> int:
    jobs = (
        session.scalars(select(Job).where(Job.run_id == run_id, Job.status.in_(from_statuses)))
    ).all()
    for job in jobs:
        job.status = to
        if to == "cancelled":
            job.finished_at = func.now()
    session.flush()
    return len(jobs)


def pause_jobs(session: Session, run_id: int) -> int:
    """Pause a run's waiting jobs; a running job is never touched."""
    return _move_jobs(session, run_id, ("queued",), "paused")


def resume_jobs(session: Session, run_id: int) -> int:
    """Paused jobs wait again; finished and running ones are left alone."""
    return _move_jobs(session, run_id, ("paused",), "queued")


def requeue_failed_jobs(session: Session, run_id: int) -> int:
    """A human retry: failed jobs wait again with fresh attempts; done ones stay."""
    jobs = session.scalars(select(Job).where(Job.run_id == run_id, Job.status == "failed")).all()
    for job in jobs:
        job.status = "queued"
        job.attempts = 0
        job.locked_at = None
        job.heartbeat_at = None
        job.worker = None
        job.run_after = datetime.datetime.now(datetime.UTC)
        job.error = None
        job.finished_at = None
    session.flush()
    return len(jobs)


def cancel_jobs(session: Session, run_id: int) -> int:
    """Cancel a run's waiting and paused jobs; running ones finish first."""
    return _move_jobs(session, run_id, ("queued", "paused"), "cancelled")


def requeue_stuck_jobs(session: Session, now: datetime.datetime) -> int:
    """Jobs silent over 5 minutes wait again; after 3 tries they fail."""
    stuck = (
        session.scalars(
            select(Job).where(
                Job.status == "running",
                Job.heartbeat_at < now - STUCK_AFTER,
            )
        )
    ).all()
    for job in stuck:
        if job.attempts >= 3:
            job.status = "failed"
            job.error = GAVE_UP
            job.finished_at = now
        else:
            job.status = "queued"
            job.locked_at = None
            job.heartbeat_at = None
            job.worker = None
    session.flush()
    return len(stuck)
