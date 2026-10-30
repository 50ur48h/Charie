"""Step 5 on the real practice database, with real AI (P07.9).

Laptop only: needs `PRACTICE_DB_URL` and a Meta key. Run once with
`AI_REPLAY=record` (about $1-4 for the ten tables); later runs pass with
`AI_REPLAY=replay` for $0. Never writes to the practice data; explanations
land in the throwaway database. Writes `.temp/explain-sample.md` for the
owner's spot-check. Profiles and links only the ten tables below, then
explains them.
"""

from pathlib import Path

import pytest

from charie.learner.steps import explain_tables
from charie.learner.steps.base import SkipItem, StepContext
from charie.learner.steps.links import make_jobs as make_link_jobs
from charie.learner.steps.links import run_job as run_links
from charie.learner.steps.profile import run_job as run_profile
from charie.learner.steps.structure import run_job as run_structure
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun

TABLES = [
    "public.orders",
    "public.order_items",
    "public.restaurants",
    "public.deliveries",
    "public.coupons",
    "public.order_coupons",
    "charie.order_ingredient_usage",
    "charie.waste_events",
    "charie.inventory_daily",
    "charie.v_monthly_outlet_profit_estimate",
]


@pytest.fixture()
def practice_ctx(db_session, practice_source):
    """A step context on the throwaway database with the practice connected."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="explain_tables", version_id=version_id)
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


def _run(ctx, **payload) -> None:
    explain_tables.run_job(
        JobInfo(
            id=5,
            kind="explain_table",
            payload={"step": "explain_tables", **payload},
            run_id=ctx.run_id,
        ),
        ctx,
    )


@pytest.mark.live_ai
@pytest.mark.practice_db
def test_practice_tables_are_explained(practice_ctx, db_session) -> None:
    ctx, said = practice_ctx
    run_structure(
        JobInfo(id=1, kind="scan_structure", payload={"step": "structure"}, run_id=ctx.run_id),
        ctx,
    )
    for full in TABLES:
        assert store.get_entry(db_session, ctx.version_id, f"table.{full}") is not None, full
    skipped: list[str] = []
    for full in TABLES:
        try:
            run_profile(
                JobInfo(
                    id=2,
                    kind="profile_table",
                    payload={"table": full},
                    run_id=ctx.run_id,
                ),
                ctx,
            )
        except SkipItem as err:
            skipped.append(f"{full}: {err}")
    assert skipped == []
    for job in make_link_jobs(ctx):
        if job["from_table"] not in TABLES and job["to_table"] not in TABLES:
            continue
        try:
            run_links(
                JobInfo(
                    id=3, kind="test_link", payload={"step": "links", **job}, run_id=ctx.run_id
                ),
                ctx,
            )
        except SkipItem as err:
            skipped.append(f"{job['from_table']}->{job['to_table']}: {err}")
    assert skipped == []
    for full in TABLES:
        _run(ctx, table=full)
    lines = []
    for full in TABLES:
        entry = store.get_entry(db_session, ctx.version_id, f"table.{full}")
        assert entry is not None and (entry.details or {}).get("explained") is True
        assert entry.meaning, full
        assert entry.confidence in ("checked", "guessed"), full
        lines.append(f"## {full} ({entry.confidence})")
        lines.append(f"Meaning: {entry.meaning}")
        lines.append(f"Grain: {(entry.details or {}).get('grain')}")
        for column in store.list_entries(db_session, ctx.version_id, kinds=["column"]):
            details = column.details if isinstance(column.details, dict) else {}
            if f"{details.get('schema')}.{details.get('table')}" != full:
                continue
            if not details.get("explained"):
                continue
            profile = details.get("profile") or {}
            assert profile.get("rows_seen", 0) > 0, column.key
            lines.append(
                f"- {column.key.rpartition('.')[2]}: {column.meaning}"
                f" [{details.get('unit')}/{details.get('currency') or '-'}]"
                f" ({column.confidence}; failed: {details.get('checks_failed') or []})"
            )
        lines.append("")
    # Owner-facing spot-check artifact: the repo-root `.temp` folder,
    # created if needed (pytest runs with `backend/` as cwd, which has none).
    root = Path(__file__).resolve().parents[4]
    sample = root / ".temp" / "explain-sample.md"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("# Explain sample (practice, P07.9)\n\n" + "\n".join(lines), encoding="utf-8")
    print(f"\n--- wrote {sample} ---")
