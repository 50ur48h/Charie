"""Step 5: read uploaded documents into sections (P08.3).

The same `read_document` job runs two ways: inside a learning run (with a
`step` payload, through the shared step handler) and on its own after an
upload. Both share `process_document` below. Sections replace the old set
in one transaction, so a failed read keeps the previous readable text.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.learner.steps.base import Step, StepContext, register_step
from charie.shared.ai.errors import AiError, SpendingPaused
from charie.shared.db import session_scope
from charie.shared.documents import reader
from charie.shared.documents.sections import split_sections
from charie.shared.jobs.queue import add_job
from charie.shared.jobs.registry import JobInfo, job_handler
from charie.shared.tables.learning import Job
from charie.shared.tables.sources import Document, DocumentFile, DocumentSection

READ_JOB = "read_document"  # Matches the queue kind the upload API uses.
INDEX_JOB = "index_document"  # Queued after a successful read (P08.4).

NO_READABLE_TEXT = "No readable text was found in this file."
READ_FAILED = "Something went wrong while reading it."

STEP_NAME = "documents"


def make_jobs(ctx: StepContext) -> list[dict]:
    """One read job per new document without an active read.

    Failed documents wait for an explicit retry from the Sources screen
    (which resets them to new); the run never re-reads them on its own.
    """
    busy = {
        (job.payload or {}).get("document_id")
        for job in ctx.session.scalars(
            select(Job).where(Job.kind == READ_JOB, Job.status.in_(("queued", "running")))
        )
    }
    rows = ctx.session.scalars(
        select(Document).where(Document.status == "new").order_by(Document.id)
    ).all()
    return [{"document_id": row.id} for row in rows if row.id not in busy]


def process_document(
    session: Session, doc: Document, *, say, learning_run_id: int | None = None
) -> None:
    """Read one document and store its sections; the caller commits."""
    stored = session.get(DocumentFile, doc.id)
    if stored is None:
        _fail(session, doc, NO_READABLE_TEXT, say)
        return
    doc.status = "reading"
    doc.error = None
    doc.progress = 10
    session.flush()
    markdown, pages, unreadable = _extract(stored.content, doc, learning_run_id)
    if not markdown.strip():
        _fail(session, doc, NO_READABLE_TEXT, say)
        return
    drafts = split_sections(markdown, page_count=pages)
    session.query(DocumentSection).filter(DocumentSection.document_id == doc.id).delete()
    for position, draft in enumerate(drafts):
        session.add(
            DocumentSection(
                document_id=doc.id,
                position=position,
                heading_path=draft.heading_path,
                text_=draft.text,
                page_from=draft.page_from,
                page_to=draft.page_to,
            )
        )
    doc.pages = pages
    doc.unreadable_pages = unreadable
    doc.progress = 50
    session.flush()
    queue_index(session, doc.id)
    say("found", f"Read {doc.file_name}: {len(drafts)} section(s).")
    if unreadable:
        say("warning", f"{unreadable} page(s) couldn't be read.")


def _extract(content: bytes, doc: Document, learning_run_id: int | None) -> tuple[str, int, int]:
    """Markdown, pages and unreadable count; Markdown decodes locally."""
    if doc.file_type in ("md", "txt"):
        try:
            return content.decode("utf-8"), 0, 0
        except UnicodeDecodeError:
            raise AiError("unreadable_file", f"{doc.file_name} can't be added.") from None
    result = reader.read_document(content, filename=doc.file_name, learning_run_id=learning_run_id)
    return result.markdown, result.page_count, result.unreadable_pages


def _fail(session: Session, doc: Document, message: str, say) -> None:
    """Mark the document failed with a plain message; sections stay as they were."""
    doc.status = "failed"
    doc.error = message
    doc.progress = 0
    session.flush()
    say("warning", f"Couldn't read {doc.file_name}: {message}")


def _plain_error(doc: Document, err: Exception) -> str:
    if isinstance(err, AiError):
        return err.message
    return READ_FAILED


def queue_index(session: Session, document_id: int) -> None:
    """Queue the note-and-embed job unless one is already waiting or running."""
    waiting = session.scalars(
        select(Job).where(
            Job.kind == INDEX_JOB,
            Job.status.in_(("queued", "running")),
        )
    ).all()
    if any((job.payload or {}).get("document_id") == document_id for job in waiting):
        return
    add_job(session, INDEX_JOB, {"document_id": document_id})


def run_job(info: JobInfo, ctx: StepContext) -> None:
    """The in-run job: read one document, then let the shared handler advance."""
    doc = ctx.session.get(Document, (info.payload or {}).get("document_id"))
    if doc is None or doc.status == "removed":
        return
    try:
        process_document(ctx.session, doc, say=ctx.say, learning_run_id=ctx.run_id)
    except SpendingPaused:
        raise
    except Exception as err:  # noqa: BLE001 (the worker retries first; see below)
        # The worker retries a failed job twice more. Only on the last try
        # does the document itself fail, so the run keeps its earlier work
        # and the owner can retry from the Sources screen.
        if info.attempts >= 3:
            _fail(ctx.session, doc, _plain_error(doc, err), ctx.say)
            return
        raise


@job_handler(READ_JOB)
def handle_read_document(info: JobInfo) -> None:
    """Route in-run jobs through the shared handler; read standalone otherwise."""
    if info.run_id is not None and (info.payload or {}).get("step") == STEP_NAME:
        from charie.learner import runs

        runs.run_step_job(info)
        return
    with session_scope() as session:
        doc = session.get(Document, (info.payload or {}).get("document_id"))
        if doc is None or doc.status == "removed":
            return

        def quiet(kind: str, message: str, details=None) -> None:
            _ = (kind, message, details)  # No run feed outside a run; the row says it.

        try:
            process_document(session, doc, say=quiet)
        except SpendingPaused:
            raise
        except Exception as err:  # noqa: BLE001 (same retry rule as in-run)
            if info.attempts >= 3:
                _fail(session, doc, _plain_error(doc, err), quiet)
                return
            raise


def finish_step(ctx: StepContext) -> None:
    """How many documents are readable now."""
    count = ctx.session.scalar(
        select(func.count(func.distinct(DocumentSection.document_id))).where(
            DocumentSection.document_id.in_(select(Document.id).where(Document.status != "removed"))
        )
    )
    word = "document" if count == 1 else "documents"
    ctx.say("found", f"{count} {word} read.")


DOCUMENTS_STEP = Step(
    name=STEP_NAME,
    title="Read your documents",
    job_kind=READ_JOB,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="No new documents to read, so I skipped this step.",
)

register_step(DOCUMENTS_STEP)
