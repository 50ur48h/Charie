"""Refresh selection: snapshot, diff, removals and the consumed mark (P08.8).

A refresh learns only what changed since the last successfully processed
snapshot: new or changed documents, removed documents and newer owner
notes. Unchanged documents make no read, index or AI calls, and changes
made while a run is going stay pending for the next refresh. The published
knowledge keeps serving throughout; removals only touch the draft.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.knowledge.store import list_entries
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.learning import LearningRun, RefreshSnapshot
from charie.shared.tables.questions import LearnerTodo
from charie.shared.tables.sources import DocFact, Document, DocumentSection, OwnerNote


def take_snapshot(session: Session) -> dict:
    """Every active document hash plus the newest notes revision."""
    rows = session.scalars(
        select(Document).where(Document.status != "removed").order_by(Document.id)
    ).all()
    notes_rev = session.scalar(select(func.max(OwnerNote.id))) or 0
    return {"documents": {str(row.id): row.sha256 for row in rows}, "notes_rev": notes_rev}


def last_consumed(session: Session) -> dict | None:
    """The last successfully processed snapshot, or none before the first."""
    row = session.scalars(
        select(RefreshSnapshot).order_by(RefreshSnapshot.id.desc()).limit(1)
    ).first()
    return dict(row.snapshot) if row is not None else None


def save_consumed(session: Session, snapshot: dict, run_id: int) -> RefreshSnapshot:
    """Pending changes clear only for the successfully consumed snapshot."""
    row = RefreshSnapshot(snapshot=dict(snapshot), run_id=run_id)
    session.add(row)
    session.flush()
    return row


def plan(session: Session) -> dict:
    """What one refresh must learn: changed documents, removals, newer notes."""
    snap = last_consumed(session) or {"documents": {}, "notes_rev": 0}
    known = snap.get("documents", {})
    notes_rev = snap.get("notes_rev", 0)
    live = {
        row.id: row
        for row in session.scalars(
            select(Document).where(Document.status != "removed").order_by(Document.id)
        ).all()
    }
    documents = [
        doc_id
        for doc_id, row in live.items()
        if (row.status == "new" and (str(doc_id) not in known or known[str(doc_id)] != row.sha256))
        or (row.status == "reading" and row.progress == 100)
    ]
    removed = [
        int(doc_id)
        for doc_id in known
        if (row := session.get(Document, int(doc_id))) is None or row.status == "removed"
    ]
    newest_note = session.scalar(select(func.max(OwnerNote.id))) or 0
    return {
        "documents": documents,
        "removed": removed,
        "notes_id": newest_note if newest_note > notes_rev else None,
    }


def pending(session: Session) -> dict:
    """The current diff against the last consumed snapshot (banner data)."""
    diff = plan(session)
    return {
        "documents": diff["documents"],
        "removed": diff["removed"],
        "notes_changed": diff["notes_id"] is not None,
    }


def scope_for(session: Session, run_id: int | None) -> dict | None:
    """This run's refresh scope, or none for first, nightly and standalone work."""
    if run_id is None:
        return None
    run = session.get(LearningRun, run_id)
    if run is None:
        return None
    scope = (run.progress or {}).get("refresh")
    return dict(scope) if isinstance(scope, dict) else None


REFRESH_STEPS = ["owner_notes", "documents", "doc_facts"]


def refresh_steps() -> list[str]:
    """Refresh steps in canonical order, only when registered."""
    from charie.learner.steps.base import STEPS

    return [name for name in REFRESH_STEPS if name in STEPS]


def begin(session: Session, kind: str = "refresh", reason: str | None = None):
    """Snapshot, queue only the changes, and mark removals; the run learns them."""
    from charie.learner import runs

    snapshot = take_snapshot(session)
    diff = plan(session)
    scope = {
        "snapshot": snapshot,
        "documents": diff["documents"],
        "notes_id": diff["notes_id"],
        "removed": diff["removed"],
    }
    run = runs.start_run(session, kind, refresh_steps(), reason, extra_progress={"refresh": scope})
    marked = apply_removals(session, run.version_id, diff["removed"])
    if marked:
        from charie.learner.events import add_event

        add_event(
            session,
            run.id,
            "info",
            f"Marked {marked} fact(s) from removed files for review.",
            step=run.step,
        )
    return run


def consume(session: Session, run: LearningRun) -> None:
    """Save the start snapshot when a learning run succeeds; failures keep it pending."""
    progress = run.progress or {}
    scope = progress.get("refresh")
    if not isinstance(scope, dict):
        scope = progress.get("refresh_snapshot")
    if not isinstance(scope, dict) or "snapshot" not in scope:
        return
    save_consumed(session, scope["snapshot"], run.id)
    from charie.learner import runs as learner_runs
    from charie.learner.events import add_event
    from charie.learner.steps import todos as todos_step

    try:
        todos_step.handle_todos(learner_runs._context(session, run))
    except Exception as err:  # noqa: BLE001 (a stuck to-do never fails the refresh)
        add_event(
            session,
            run.id,
            "warning",
            f"Couldn't work through the to-do list: {err}.",
            step=run.step,
        )
    session.flush()


def apply_removals(session: Session, version_id: int, removed_ids: list[int]) -> int:
    """Facts from removed content need checking; dependent draft entries get a to-do."""
    removed = {int(doc_id) for doc_id in removed_ids}
    if not removed:
        return 0
    facts = session.scalars(select(DocFact).where(DocFact.document_id.in_(removed))).all()
    marked = 0
    for fact in facts:
        if fact.status != "needs_checking":
            fact.status = "needs_checking"
            marked += 1
    session.flush()
    _flag_orphaned_entries(session, version_id, removed)
    return marked


def _flag_orphaned_entries(session: Session, version_id: int, removed: set[int]) -> None:
    """One correction to-do per draft entry sourced only from removed documents."""
    section_ids: set[int] = set()
    entries = list_entries(session, version_id)
    for entry in entries:
        for source in entry.sources or []:
            if isinstance(source, dict) and source.get("type") == "document":
                section_id = source.get("section_id")
                if isinstance(section_id, int):
                    section_ids.add(section_id)
    owners: dict[int, int] = {}
    if section_ids:
        rows = session.scalars(
            select(DocumentSection).where(DocumentSection.id.in_(section_ids))
        ).all()
        owners = {row.id: row.document_id for row in rows}
    open_keys = {
        (todo.details or {}).get("key")
        for todo in session.scalars(
            select(LearnerTodo).where(
                LearnerTodo.status == "open", LearnerTodo.kind == "correction"
            )
        ).all()
    }
    version = session.get(KbVersion, version_id)
    for entry in entries:
        sources = entry.sources or []
        if not sources or any(
            not isinstance(source, dict) or source.get("type") != "document" for source in sources
        ):
            continue
        doc_ids = {
            owners[section_id]
            for source in sources
            if (section_id := source.get("section_id")) in owners
        }
        if not doc_ids or any(doc_id not in removed for doc_id in doc_ids):
            continue
        if entry.key in open_keys:
            continue
        file_name = next(
            (source.get("document") for source in sources if source.get("document")),
            "a removed file",
        )
        session.add(
            LearnerTodo(
                kind="correction",
                text_=f"{entry.title}: its source file {file_name} was removed",
                details={
                    "key": entry.key,
                    "version": version.number if version else None,
                    "document": file_name,
                },
                status="open",
            )
        )
    session.flush()
