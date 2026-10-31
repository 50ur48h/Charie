"""The worker's run lock must let AI cost rows through (P07.10).

`run_step_job` holds the learning run row while step work runs. The
default DbCostLog inserts `ai_calls` rows in their own transaction with a
foreign key to the run, so FOR UPDATE blocked those checks and the
worker stuck. FOR NO KEY UPDATE is compatible with them.
"""

from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text

from charie.learner import runs
from charie.learner.steps.base import STEPS, Step, register_step
from charie.learner.steps.explain_tables import ExplainTableForm
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import DbCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.db import clear_engine_cache, session_scope
from charie.shared.jobs.registry import HANDLERS, JobInfo
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.usage import AiCall


def _alter_db(url: str, setting: str) -> None:
    """Run one ALTER DATABASE outside a transaction, then drop cached engines."""
    parts = urlparse(url)
    server = create_engine(
        urlunparse(parts._replace(path="/postgres")), isolation_level="AUTOCOMMIT"
    )
    with server.connect() as conn:
        conn.execute(text(f'ALTER DATABASE "{parts.path.lstrip("/")}" {setting}'))
    server.dispose()
    clear_engine_cache()


@pytest.fixture()
def bounded_locks(test_db_url):
    """Fail fast instead of hanging if the run lock ever blocks again."""
    _alter_db(test_db_url, "SET lock_timeout = '5s'")
    try:
        yield
    finally:
        _alter_db(test_db_url, "RESET lock_timeout")


@pytest.fixture()
def ai_step():
    """One canonical step whose work is a real AI call (fake AI, real cost log)."""
    saved_steps = dict(STEPS)
    saved_handlers = dict(HANDLERS)
    STEPS.clear()
    HANDLERS.clear()
    fake = FakeAi().reply(
        "explain_table", {"table_meaning": "One row is one order.", "grain": "one order"}
    )

    def run_job(info, ctx) -> None:
        AiClient(provider=fake, cost_log=DbCostLog(), sleep=lambda s: None).run(
            "explain_table",
            {"table": {"name": "orders"}, "owner_rules": "None."},
            ExplainTableForm,
            app="learner",
            learning_run_id=ctx.run_id,
        )

    step = Step(
        name="owner_notes",
        title="Read your notes",
        job_kind="test_owner_notes",
        make_jobs=lambda ctx: [{"n": 1}],
        run_job=run_job,
        finish=lambda ctx: None,
    )
    register_step(step)
    runs.register_step_handler("owner_notes")
    yield fake
    for name in list(STEPS):
        del STEPS[name]
        del HANDLERS[f"test_{name}"]
    STEPS.update(saved_steps)
    HANDLERS.update(saved_handlers)


def test_worker_cost_insert_reaches_database(db, bounded_locks, ai_step) -> None:
    """The AI cost row lands while the worker holds the run lock."""
    with session_scope() as session:
        run = runs.start_run(session, "first", ["owner_notes"])
        run_id = run.id
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
        run = session.get(LearningRun, run_id)
        assert run is not None
        assert run.status == "done"
        rows = [
            (row.job, row.status)
            for row in session.query(AiCall).filter(AiCall.learning_run_id == run_id).all()
        ]
    assert ai_step.calls and ai_step.calls[0][0] == "explain_table"
    assert rows == [("explain_table", "ok")]
