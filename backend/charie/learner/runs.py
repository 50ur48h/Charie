"""Learning runs: start, dispatch, advance, pause, resume (P07.1)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from charie.learner.api.sources import saved_password, saved_source
from charie.learner.events import add_event
from charie.learner.locks import RunActiveError, serialize_learning_runs
from charie.learner.steps.base import (
    STEP_NUMBERS,
    STEPS,
    Step,
    StepContext,
    register_step_handler,
)
from charie.shared.ai.errors import SpendingPaused
from charie.shared.ai.spending import month_spent, spending_state
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.db import session_scope
from charie.shared.jobs.queue import (
    add_job,
    finish_job,
    pause_jobs,
    requeue_failed_jobs,
    resume_jobs,
)
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge.versions import get_or_create_draft
from charie.shared.settings import get_setting
from charie.shared.tables.learning import Job, LearningRun

ACTIVE_STATUSES = ("running", "paused")
TERMINAL_STATUSES = ("done", "failed")

MADE_BY = {"first": "first_learning", "refresh": "refresh", "nightly": "nightly"}


# Re-exported so existing imports keep working; locks.py owns it.
__all__ = ["RunActiveError", "register_step_handler"]


def active_run(session: Session) -> LearningRun | None:
    """The running or paused run, if any."""
    return session.scalar(
        select(LearningRun).where(LearningRun.status.in_(ACTIVE_STATUSES)).limit(1)
    )


def _fresh_progress(steps: list[str]) -> dict:
    """One progress entry per step; done and total fill in as jobs queue."""
    return {
        "order": list(steps),
        "steps": {name: {"done": 0, "total": 0, "jobs": []} for name in steps},
        "done_steps": [],
    }


def _made_by(kind: str) -> str:
    if kind not in MADE_BY:
        raise ValueError(f"Run kind `{kind}` is not first, refresh or nightly.")
    return MADE_BY[kind]


def start_run(
    session: Session, kind: str, steps: list[str], reason: str | None = None
) -> LearningRun:
    """Start one run; a second start while one is active is refused.

    Creates the run, its progress and its draft version, queues the first
    step's jobs and writes the first feed line — all in one transaction.
    """
    ordered = [name for name in STEP_NUMBERS if name in steps]
    unknown = [name for name in steps if name not in STEP_NUMBERS]
    if unknown:
        raise ValueError(f"Unknown learning steps: {', '.join(unknown)}.")
    for name in ordered:
        if name not in STEPS:
            raise ValueError(f"Step `{name}` has no implementation yet.")
    serialize_learning_runs(session)
    active = session.scalar(
        select(LearningRun).where(LearningRun.status.in_(ACTIVE_STATUSES)).limit(1)
    )
    if active is not None:
        raise RunActiveError(f"A learning run is already {active.status}.")
    draft = get_or_create_draft(session, _made_by(kind))
    run = LearningRun(
        kind=kind,
        reason=reason,
        status="running",
        step=ordered[0] if ordered else None,
        progress=_fresh_progress(ordered),
        version_id=draft.id,
    )
    session.add(run)
    session.flush()
    if ordered:
        _queue_step(session, run, STEPS[ordered[0]])
    else:
        _finish_run(session, run, "Nothing to learn yet.")
    return run


def _context(session: Session, run: LearningRun) -> StepContext:
    """The handler context: source, connector, settings and a feed writer."""

    source = saved_source(session)
    connector = None
    if source is not None:
        password = saved_password(session)
        connector = PostgresConnector(
            source.host, source.port, source.database, source.username, password
        )

    def say(kind: str, message: str, details: dict | None = None) -> None:
        add_event(session, run.id, kind, message, step=run.step, details=details or {})

    return StepContext(
        session=session,
        run_id=run.id,
        version_id=run.version_id,
        source=source,
        connector=connector,
        strict_mode=bool(get_setting(session, "strict_mode")),
        settings={},
        say=say,
    )


def _queue_step(session: Session, run: LearningRun, step: Step) -> None:
    """Queue one job per payload the step makes, and open the step on the feed."""
    ctx = _context(session, run)
    payloads = step.make_jobs(ctx)
    ids = [
        add_job(session, step.job_kind, dict(payload, step=step.name), run_id=run.id)
        for payload in payloads
    ]
    entry = run.progress["steps"][step.name]
    entry["total"] = len(ids)
    entry["jobs"] = ids
    if not ids:
        entry["note"] = step.empty_note
    flag_modified(run, "progress")
    total = len(run.progress["order"])
    position = run.progress["order"].index(step.name) + 1
    ctx.say("info", f"Step {position} of {total}: {step.title}.")
    if not ids:
        # Nothing to run: move on now, since no worker ever will.
        advance_run(session, run.id)


def _record_step_progress(session: Session, run: LearningRun, name: str) -> None:
    """Persist how many of the step's jobs are done (recomputed, so retries stay honest)."""
    jobs = _step_jobs(session, run, name)
    entry = run.progress["steps"][name]
    entry["done"] = sum(1 for job in jobs if job.status == "done")
    entry["total"] = len(jobs)
    flag_modified(run, "progress")


def _step_jobs(session: Session, run: LearningRun, name: str) -> list[Job]:
    """The prepared jobs of one step, in queue order."""
    ids = run.progress["steps"][name]["jobs"]
    if not ids:
        return []
    return list(session.scalars(select(Job).where(Job.id.in_(ids)).order_by(Job.id)))


def advance_run(session: Session, run_id: int) -> None:
    """Move a running run on: finish done steps, queue the next one, or finish.

    Only runs when every prepared job of the current step is done. Paused,
    done and failed runs are left alone; finished steps never finish twice.
    """
    run = session.get(LearningRun, run_id, with_for_update=True)
    if run is None or run.status in TERMINAL_STATUSES or run.step is None:
        return
    jobs = _step_jobs(session, run, run.step)
    if any(job.status == "failed" for job in jobs):
        fail_run(session, run_id, f"{STEPS[run.step].title} failed.")
        return
    if any(job.status != "done" for job in jobs):
        return
    if run.step not in run.progress["done_steps"]:
        STEPS[run.step].finish(_context(session, run))
        run.progress["done_steps"].append(run.step)
        flag_modified(run, "progress")
    if run.status != "running":
        return
    order = run.progress["order"]
    remaining = order[order.index(run.step) + 1 :]
    if not remaining:
        _finish_run(session, run, None)
        return
    run.step = remaining[0]
    _queue_step(session, run, STEPS[remaining[0]])


def _finish_run(session: Session, run: LearningRun, summary: str | None) -> None:
    """Close a run once: status, time, feed line. Never runs twice."""
    if run.status == "done":
        return
    run.status = "done"
    run.finished_at = datetime.now(UTC)
    if summary is not None:
        run.summary = summary
    duration = run.finished_at - run.started_at
    add_event(
        session,
        run.id,
        "done",
        f"All done in {_duration_text(duration)}.",
        step=run.step,
    )


def _duration_text(duration: timedelta) -> str:
    """`90 seconds` → "2 minutes"; always plain words."""
    seconds = max(1, int(duration.total_seconds()))
    if seconds < 60:
        return f"{seconds} second" + ("" if seconds == 1 else "s")
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    hours = minutes // 60
    return f"{hours} hour" + ("" if hours == 1 else "s")


def fail_run(session: Session, run_id: int, error: str) -> None:
    """Fail a run once: status, time, summary and one warning line."""
    run = session.get(LearningRun, run_id, with_for_update=True)
    if run is None or run.status in TERMINAL_STATUSES:
        return
    run.status = "failed"
    run.finished_at = datetime.now(UTC)
    run.summary = error
    add_event(session, run.id, "warning", error, step=run.step)


def pause_run(session: Session, run_id: int, by: str) -> bool:
    """Pause a running run; queued work waits, a running job finishes first."""
    run = session.get(LearningRun, run_id, with_for_update=True)
    if run is None or run.status != "running":
        return False
    run.status = "paused"
    run.paused_by = by
    pause_jobs(session, run_id)
    add_event(
        session,
        run.id,
        "info",
        "Learning is paused. Nothing learned so far is lost.",
        step=run.step,
    )
    return True


def _spending_ok(session: Session) -> bool:
    """The month's AI bill is still under the limit."""
    spent = month_spent(session, datetime.now(UTC))
    limit = get_setting(session, "spend_limit_usd")
    warn = get_setting(session, "spend_warn_percent")
    return spending_state(spent, limit, warn) != "paused"


def resume_run(session: Session, run_id: int) -> bool:
    """Resume a paused run, or retry a failed one from where it stopped.

    Spending-paused runs and failed retries need budget room first; a
    failed retry requeues only failed jobs with fresh attempts, so done
    work is never repeated. Queued (unrun) jobs simply wait again.
    """
    serialize_learning_runs(session)
    run = session.get(LearningRun, run_id, with_for_update=True)
    if run is None or run.status not in ("paused", "failed"):
        return False
    other = session.scalar(
        select(LearningRun.id)
        .where(LearningRun.status.in_(ACTIVE_STATUSES), LearningRun.id != run_id)
        .limit(1)
    )
    if other is not None:
        raise RunActiveError("A learning run is already going.")
    was_failed = run.status == "failed"
    if not _spending_ok(session):
        return False
    run.status = "running"
    run.paused_by = None
    run.finished_at = None
    if was_failed:
        requeue_failed_jobs(session, run_id)
        add_event(
            session,
            run.id,
            "info",
            "Trying again from where it stopped. Finished work is kept.",
            step=run.step,
        )
    else:
        resume_jobs(session, run_id)
    advance_run(session, run_id)
    return True


def resume_after_spending_raise(session: Session, run_id: int) -> bool:
    """Resume budget-paused work after the budget check passes; nothing else."""
    serialize_learning_runs(session)
    run = session.get(LearningRun, run_id, with_for_update=True)
    if run is None or run.status != "paused" or run.paused_by != "spending":
        return False
    other = session.scalar(
        select(LearningRun.id)
        .where(LearningRun.status.in_(ACTIVE_STATUSES), LearningRun.id != run_id)
        .limit(1)
    )
    if other is not None:
        raise RunActiveError("A learning run is already going.")
    if not _spending_ok(session):
        return False
    run.status = "running"
    run.paused_by = None
    resume_jobs(session, run_id)
    advance_run(session, run_id)
    return True


def run_step_job(info: JobInfo) -> None:
    """The handler for step jobs: do the step's work, then advance the run.

    Step work runs inside a savepoint: a failed attempt rolls its partial
    writes back, while the run and job failure settle durably in the
    outer transaction — even when the step broke the database.
    """
    with session_scope() as session:
        run = session.get(LearningRun, info.run_id, with_for_update=True)
        if run is None or run.status in TERMINAL_STATUSES:
            return
        name = dict(info.payload).get("step", "")
        step = STEPS.get(name)
        if step is None:
            raise ValueError(f"Step `{name}` is not registered.")
        ctx = _context(session, run)
        savepoint = session.begin_nested()
        try:
            step.run_job(info, ctx)
        except SpendingPaused:
            savepoint.rollback()
            pause_run(session, run.id, "spending")
            session.commit()
            raise
        except Exception as err:
            savepoint.rollback()
            if info.attempts >= 3:
                fail_run(session, run.id, f"{step.title} failed: {err}.")
                session.commit()
            raise
        finish_job(session, info.id, "done")
        _record_step_progress(session, run, name)
        advance_run(session, run.id)
