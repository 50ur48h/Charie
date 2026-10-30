"""`GET /api/learning`, start/refresh/pause/resume and the live stream (P07.1)."""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.learner import runs
from charie.learner.events import feed_lines
from charie.learner.steps.base import STEP_NUMBERS, STEPS
from charie.shared.db import get_session, session_scope
from charie.shared.errors import ApiError
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.learning import LearningRun

learning_router = APIRouter()


class StepProgressOut(BaseModel):
    step: int
    done: int
    total: int | None
    note: str


class LearningRunOut(BaseModel):
    id: int
    kind: str
    status: str
    reason: str | None
    step: int
    percent: int
    minutes_left: int | None
    progress: list[StepProgressOut]
    cost_usd: float
    summary: str | None
    version_number: int
    new_version: bool
    started_at: str
    finished_at: str | None
    paused_by: str | None


class LearningOverviewOut(BaseModel):
    runs: list[LearningRunOut]


class StartRunIn(BaseModel):
    kind: str = "first"
    reason: str | None = None


class RefreshRunIn(BaseModel):
    reason: str | None = None


class PauseOut(BaseModel):
    status: str


class ResumeOut(BaseModel):
    status: str


def _progress_entries(run: LearningRun) -> tuple[list[StepProgressOut], int]:
    """Per-step done/total in canonical order, plus the overall percent."""
    steps = run.progress.get("steps", {})
    order = run.progress.get("order", list(steps))
    done = sum(entry.get("done", 0) for entry in steps.values())
    total = sum(entry.get("total", 0) for entry in steps.values())
    entries = [
        StepProgressOut(
            step=STEP_NUMBERS.get(name, 0),
            done=steps[name].get("done", 0),
            total=steps[name].get("total", 0) or None,
            note="",
        )
        for name in order
        if name in steps
    ]
    return entries, round(done / total * 100) if total else 0


def run_shape(session: Session, run: LearningRun) -> dict:
    """The `LearningRun` the screens expect (frontend `learner-types.ts`)."""
    entries, percent = _progress_entries(run)
    version = session.get(KbVersion, run.version_id) if run.version_id else None
    return {
        "id": run.id,
        "kind": run.kind,
        "status": run.status,
        "reason": run.reason,
        "step": STEP_NUMBERS.get(run.step or "", 0),
        "percent": percent,
        "minutes_left": None,
        "progress": [entry.model_dump() for entry in entries],
        "cost_usd": float(run.cost_usd),
        "summary": run.summary,
        "version_number": version.number if version is not None else 0,
        "new_version": run.version_id is not None,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "paused_by": run.paused_by,
    }


def _overview(session: Session) -> dict:
    """All runs, newest first."""
    ordered = session.scalars(select(LearningRun).order_by(LearningRun.id.desc()))
    return {"runs": [run_shape(session, run) for run in ordered]}


def _start(session: Session, kind: str, reason: str | None) -> dict:
    """Start with every registered step, in canonical order."""
    try:
        run = runs.start_run(session, kind, list(STEPS), reason)
    except runs.RunActiveError as err:
        raise ApiError(409, "run_active", str(err)) from err
    except ValueError as err:
        raise ApiError(400, "bad_request", str(err)) from err
    session.commit()
    return run_shape(session, run)


@learning_router.get("/api/learning", response_model=LearningOverviewOut)
def get_learning(session: Session = Depends(get_session)) -> dict:
    return _overview(session)


@learning_router.post("/api/learning/start", response_model=LearningRunOut, status_code=201)
def post_start(body: StartRunIn, session: Session = Depends(get_session)) -> dict:
    return _start(session, body.kind, body.reason)


@learning_router.post("/api/learning/refresh", response_model=LearningRunOut, status_code=201)
def post_refresh(body: RefreshRunIn, session: Session = Depends(get_session)) -> dict:
    return _start(session, "refresh", body.reason)


@learning_router.post("/api/learning/pause", response_model=PauseOut)
def post_pause(session: Session = Depends(get_session)) -> dict:
    run = runs.active_run(session)
    if run is None:
        raise ApiError(404, "no_active_run", "No learning run is going right now.")
    runs.pause_run(session, run.id, "user")
    session.commit()
    return {"status": "paused"}


@learning_router.post("/api/learning/resume", response_model=ResumeOut)
def post_resume(session: Session = Depends(get_session)) -> dict:
    run = session.scalar(
        select(LearningRun)
        .where(LearningRun.status.in_(("paused", "failed")))
        .order_by(LearningRun.id.desc())
        .limit(1)
    )
    if run is None:
        raise ApiError(404, "nothing_to_resume", "No paused or stopped learning run to resume.")
    if not runs.resume_run(session, run.id):
        raise ApiError(
            409,
            "spending_paused",
            "The AI budget is spent. Raise the limit to keep learning.",
        )
    session.commit()
    return {"status": "running"}


@learning_router.get("/api/learning/stream")
def get_stream(
    request: Request,
    run_id: int = Query(...),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """The live feed: replay missed lines, then stream new ones (09)."""
    run = session.get(LearningRun, run_id)
    if run is None:
        raise ApiError(404, "no_such_run", "No learning run with that id.")
    last_id = request.headers.get("last-event-id", "0")
    try:
        seen = int(str(last_id).strip() or "0")
    except ValueError:
        seen = 0

    def make_session():
        return session_scope()

    return StreamingResponse(
        feed_lines(make_session, run_id, seen),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
