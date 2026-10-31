"""Step 3 on the real practice database: every column gets a profile (P07.7).

Laptop only: needs `PRACTICE_DB_URL`. Never writes to the practice data;
profiles land in the throwaway database. Prints how long profiling took.
"""

import time

import pytest

from charie.learner.steps import profile
from charie.learner.steps.base import SkipItem, StepContext
from charie.learner.steps.structure import run_job as run_structure
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun


@pytest.fixture()
def practice_ctx(db_session, practice_source):
    """A step context on the throwaway database with the practice connected."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="profile", version_id=version_id)
    db_session.add(run)
    db_session.commit()
    said: list = []
    return (
        StepContext(
            session=db_session,
            run_id=run.id,
            version_id=version_id,
            source=practice_source["source"],
            connector=practice_source["connector"],
            strict_mode=False,
            settings={},
            say=lambda kind, message, details=None: said.append((kind, message)),
        ),
        said,
    )


@pytest.mark.practice_db
def test_every_practice_column_has_a_profile(practice_ctx, db_session) -> None:
    ctx, _ = practice_ctx
    run_structure(
        JobInfo(id=1, kind="scan_structure", payload={"step": "structure"}, run_id=ctx.run_id),
        ctx,
    )
    # Every table and every view: the plan needs a profile on each column.
    tables = store.list_entries(db_session, ctx.version_id, kinds=["table"])
    assert tables
    started = time.monotonic()
    skipped: list[str] = []
    for entry in tables:
        details = entry.details or {}
        try:
            profile.run_job(
                JobInfo(
                    id=2,
                    kind="profile_table",
                    payload={"table": f"{details.get('schema')}.{details.get('name')}"},
                    run_id=ctx.run_id,
                ),
                ctx,
            )
        except SkipItem as err:
            skipped.append(f"{details.get('schema')}.{details.get('name')}: {err}")
    elapsed = time.monotonic() - started
    assert skipped == []
    columns = store.list_entries(db_session, ctx.version_id, kinds=["column"])
    missing = [entry.key for entry in columns if not (entry.details or {}).get("profile")]
    assert missing == []
    profiled = [
        entry
        for entry in store.list_entries(db_session, ctx.version_id, kinds=["table"])
        if (entry.details or {}).get("profiled_at")
    ]
    print(f"\n--- profiled {len(profiled)} tables, {len(columns)} columns in {elapsed:.0f}s ---")
    assert len(profiled) == len(tables)
