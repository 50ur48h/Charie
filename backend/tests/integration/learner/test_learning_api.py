"""GET /api/learning shape, /api/status learning counts, failed-run retry (P07.2)."""

import pytest

from charie.learner import runs
from charie.learner.steps.base import STEPS, Step, register_step
from charie.shared.db import session_scope
from charie.shared.jobs.registry import HANDLERS, JobInfo
from tests.conftest import log_in
from tests.integration.learner.test_runs import _events, _first_job, _run

RUN_KEYS = {
    "id",
    "kind",
    "status",
    "paused_by",
    "reason",
    "step",
    "percent",
    "minutes_left",
    "progress",
    "cost_usd",
    "summary",
    "version_number",
    "new_version",
    "started_at",
    "finished_at",
}

PROGRESS_KEYS = {"step", "done", "total", "note"}


@pytest.fixture
def two_steps():
    """Two canonical fixture steps; real steps are stowed and restored."""
    saved_steps = dict(STEPS)
    saved_handlers = dict(HANDLERS)
    STEPS.clear()
    HANDLERS.clear()
    log: list = []
    fail: set[str] = set()

    def make(name: str, title: str) -> None:
        def make_jobs(ctx) -> list:
            return [{"n": 1}]

        def run_job(info, ctx) -> None:
            log.append(("run", name))
            if name in fail:
                fail.discard(name)
                raise RuntimeError(f"{name} broke")

        step = Step(
            name=name,
            title=title,
            job_kind=f"test_{name}",
            make_jobs=make_jobs,
            run_job=run_job,
            finish=lambda ctx: log.append(("finish", name)),
        )
        register_step(step)
        runs.register_step_handler(name)

    for step_name, title in [
        ("owner_notes", "Read your notes"),
        ("structure", "Study the database structure"),
    ]:
        make(step_name, title)
    try:
        yield log, fail
    finally:
        for name in ("owner_notes", "structure"):
            step = STEPS.pop(name)
            del HANDLERS[step.job_kind]
        STEPS.update(saved_steps)
        HANDLERS.update(saved_handlers)


def _start(client) -> dict:
    response = client.post("/api/learning/start", json={"kind": "first"})
    assert response.status_code == 201, response.text
    return response.json()


def test_response_matches_frontend(learner_client, db, two_steps) -> None:
    log_in(learner_client)
    started = _start(learner_client)
    assert set(started.keys()) == RUN_KEYS
    assert started["status"] == "running"
    assert started["step"] == 1
    assert started["paused_by"] is None
    body = learner_client.get("/api/learning")
    assert body.status_code == 200, body.text
    assert set(body.json().keys()) == {"runs"}
    (overview,) = body.json()["runs"]
    assert set(overview.keys()) == RUN_KEYS
    assert overview["id"] == started["id"]
    assert overview["progress"], "a started run reports its saved step counts"
    for entry in overview["progress"]:
        assert set(entry.keys()) == PROGRESS_KEYS
    assert [entry["step"] for entry in overview["progress"]] == [1, 2]


def test_status_learning(learner_client, db, two_steps) -> None:
    log_in(learner_client)
    status = learner_client.get("/api/status")
    assert status.status_code == 200, status.text
    assert status.json()["learning"] == {"status": "none", "step_title": None, "percent": 0}
    _start(learner_client)
    status = learner_client.get("/api/status")
    assert status.status_code == 200, status.text
    assert status.json()["learning"] == {
        "status": "running",
        "step_title": "Read your notes",
        "percent": 0,
    }


def test_resume_failed_run_requeues_only_failed(learner_client, db, two_steps) -> None:
    log, fail = two_steps
    log_in(learner_client)
    run_id = _start(learner_client)["id"]
    fail.add("structure")
    runs.run_step_job(_first_job(run_id, "owner_notes"))
    info = _first_job(run_id, "structure")
    failing = JobInfo(id=info.id, kind=info.kind, payload=info.payload, run_id=run_id, attempts=3)
    with pytest.raises(RuntimeError, match="structure broke"):
        runs.run_step_job(failing)
    assert _run(run_id).status == "failed"
    response = learner_client.post("/api/learning/resume")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "running"}
    assert _run(run_id).finished_at is None
    assert sum("Trying again" in message for message in _events(run_id)) == 1
    # The failed step runs again and finishes; the done step never repeats.
    runs.run_step_job(_first_job(run_id, "structure"))
    assert log.count(("run", "owner_notes")) == 1
    assert log.count(("run", "structure")) == 2
    assert log.count(("finish", "structure")) == 1
    assert _run(run_id).status == "done"


def test_resume_failed_run_needs_budget(learner_client, db, two_steps, monkeypatch) -> None:
    log_in(learner_client)
    run_id = _start(learner_client)["id"]
    with session_scope() as session:
        runs.fail_run(session, run_id, "structure broke.")
    monkeypatch.setattr(runs, "_spending_ok", lambda session: False)
    response = learner_client.post("/api/learning/resume")
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "spending_paused"
    assert _run(run_id).status == "failed"


def test_resume_nothing_to_retry(learner_client, db) -> None:
    log_in(learner_client)
    response = learner_client.post("/api/learning/resume")
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "nothing_to_resume"


def test_raising_limit_continues_spending_paused_run(learner_client, db, two_steps) -> None:
    """Raising the limit resumes a spending-paused run and logs the message."""
    from decimal import Decimal

    from charie.shared.settings import set_setting
    from charie.shared.tables.usage import AiCall

    log_in(learner_client)
    run_id = _start(learner_client)["id"]
    with session_scope() as session:
        session.add(
            AiCall(
                app="tests",
                job="write_answer",
                provider="meta",
                model="muse-wonder-1.0",
                cost_usd=Decimal("10"),
            )
        )
        session.commit()
        set_setting(session, "spend_limit_usd", 5)
        assert runs.pause_run(session, run_id, "spending") is True
        session.commit()
    assert _run(run_id).status == "paused"
    response = learner_client.patch("/api/settings", json={"spend_limit_usd": 150})
    assert response.status_code == 200, response.text
    assert _run(run_id).status == "running"
    assert any("Continuing paused run." in message for message in _events(run_id))
