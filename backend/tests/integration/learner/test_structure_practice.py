"""Step 2 on the real practice database: all objects and the data end (P07.6).

Laptop only: needs `PRACTICE_DB_URL`. Never writes to the practice data;
entries land in the throwaway database.
"""

import pytest

from charie.learner.steps.base import StepContext
from charie.learner.steps.structure import run_job
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.sources import DataSource


@pytest.fixture()
def practice_ctx(db_session, practice_source):
    """A step context on the throwaway database with the practice connected."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="structure", version_id=version_id)
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


def _run(ctx) -> None:
    run_job(
        JobInfo(
            id=1,
            kind="scan_structure",
            payload={"step": "structure"},
            run_id=ctx.run_id,
            attempts=1,
        ),
        ctx,
    )


@pytest.mark.practice_db
def test_practice_has_57_tables_and_views(practice_ctx, db_session) -> None:
    ctx, said = practice_ctx
    _run(ctx)
    tables = store.list_entries(db_session, ctx.version_id, kinds=["table"])
    assert len(tables) == 57
    assert sum(1 for entry in tables if entry.details["is_view"]) == 5
    assert sum(1 for entry in tables if not entry.details["is_view"]) == 52
    for entry in tables:
        assert entry.details["columns"], entry.key
    assert ("found", "Found 52 tables and 5 views, with 273 columns.") in said


@pytest.mark.practice_db
def test_practice_data_ends_31_dec_2025(practice_ctx, db_session) -> None:
    ctx, said = practice_ctx
    _run(ctx)
    span = store.get_entry(db_session, ctx.version_id, "data_range.public.orders")
    assert span is not None
    assert span.details["date_to"] == "2025-12-31"
    assert span.meaning.endswith(" to 31 Dec 2025 (column created_at).")
    source = db_session.get(DataSource, ctx.source.id)
    assert source.data_through is not None
    assert source.data_through.date().isoformat() == "2025-12-31"
    assert ("found", "The newest data is from 31 Dec 2025.") in said
