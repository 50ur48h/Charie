"""Step 6: pull facts out of the documents, with exact quotes (P08.6).

Each section's facts are extracted with the AI, but code checks every
quote really appears before anything is written. Supported kinds become
knowledge entries (confidence from a document); reported numbers and
formulas stay document claims for later checks. A second extraction of
the same section replaces its facts, never duplicates them.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from charie.learner.steps.base import Step, StepContext, register_step, register_step_handler
from charie.learner.steps.refresh import scope_for
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import AiError, SpendingPaused
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge.keys import slug
from charie.shared.knowledge.store import get_entry, upsert_entry
from charie.shared.search.search import index_entry
from charie.shared.tables.learning import Job, LearningRun
from charie.shared.tables.sources import DocFact, Document, DocumentSection
from charie.shared.text.quotes import normalize_text, quote_appears

EXTRACT_JOB = "extract_doc_facts"
COMPARE_JOB = "compare_facts"

STEP_NAME = "doc_facts"
KNOWLEDGE_KINDS = ("definition", "rule", "code", "event")

FactKind = Literal["definition", "formula", "rule", "code", "event", "reported_number"]


class DocFactForm(BaseModel):
    """One fact the section states, with its exact quote."""

    model_config = ConfigDict(extra="forbid")

    kind: FactKind = Field(description="One of the six fact kinds.")
    topic: str = Field(description="The short name the fact is about.")
    statement: str = Field(description="The fact in plain words; nothing beyond the quote.")
    quote: str = Field(description="The exact words from the section.")
    location: str = Field(default="", description="Where in the section the quote sits.")


class ExtractDocFactsForm(BaseModel):
    """The fixed form the extraction job answers in."""

    model_config = ConfigDict(extra="forbid")

    facts: list[DocFactForm] = Field(default=[], description="The facts the section states.")


class CompareFactsForm(BaseModel):
    """The fixed form the comparison job answers in."""

    model_config = ConfigDict(extra="forbid")

    agree: bool = Field(description="True when the statements say the same thing.")
    topic: str = Field(default="", description="The topic that was judged.")


def make_jobs(ctx: StepContext) -> list[dict]:
    """One extraction job per fully indexed document without an active job."""
    busy = {
        (job.payload or {}).get("document_id")
        for job in ctx.session.scalars(
            select(Job).where(Job.kind == EXTRACT_JOB, Job.status.in_(("queued", "running")))
        )
    }
    rows = ctx.session.scalars(
        select(Document).where(Document.status == "reading", Document.progress == 100)
    ).all()
    jobs = [{"document_id": row.id} for row in rows if row.id not in busy]
    scope = scope_for(ctx.session, ctx.run_id)
    if scope is not None:
        wanted = set(scope["documents"])
        jobs = [job for job in jobs if job["document_id"] in wanted]
    return jobs


def extract_document(
    session: Session, doc: Document, *, say, version_id: int, run_id: int | None
) -> int:
    """Extract every section's facts, persist them and index the entries."""
    sections = session.scalars(
        select(DocumentSection)
        .where(DocumentSection.document_id == doc.id)
        .order_by(DocumentSection.position)
    ).all()
    if not sections:
        _fail(session, doc, "No readable text was found in this file.", say)
        return 0
    learned_at = datetime.now(UTC)
    total = 0
    for section in sections:
        form = get_ai().run(
            EXTRACT_JOB,
            {"heading": section.heading_path or "", "section": section.text_},
            ExtractDocFactsForm,
            app="learner",
            learning_run_id=run_id,
        )
        kept = [fact for fact in form.facts if _valid(fact, section)]
        dropped = len(form.facts) - len(kept)
        if dropped:
            say("warning", f"I left out {dropped} fact(s) whose quotes aren't in the text.")
        session.query(DocFact).filter(DocFact.section_id == section.id).delete()
        for fact in kept:
            session.add(
                DocFact(
                    document_id=doc.id,
                    section_id=section.id,
                    kind=fact.kind,
                    topic=fact.topic.strip(),
                    statement=fact.statement.strip(),
                    quote=fact.quote,
                    location=fact.location.strip() or None,
                    status="ok",
                )
            )
            _upsert_entry(session, version_id, doc, section, fact, learned_at, run_id)
        total += len(kept)
    session.flush()
    doc.fact_count = session.scalar(
        select(func.count()).select_from(DocFact).where(DocFact.document_id == doc.id)
    )
    doc.status = "learned"
    doc.learned_at = learned_at
    doc.error = None
    session.flush()
    say("found", f"Learned {total} fact(s) from {doc.file_name}.")
    return total


def _valid(fact: DocFactForm, section: DocumentSection) -> bool:
    """A fact with a topic, a statement and a quote from the section."""
    if not fact.topic.strip() or not fact.statement.strip():
        return False
    return quote_appears(fact.quote, section.text_)


def _upsert_entry(
    session: Session,
    version_id: int,
    doc: Document,
    section: DocumentSection,
    fact: DocFactForm,
    learned_at: datetime,
    run_id: int | None,
) -> None:
    """Supported kinds become knowledge; numbers and formulas stay claims."""
    if fact.kind not in KNOWLEDGE_KINDS:
        return
    key = f"doc.{fact.kind}.{slug(fact.topic)}.{doc.id}"
    at = learned_at.isoformat()
    source = {
        "type": "document",
        "quote": fact.quote,
        "at": at,
        "document": doc.file_name,
        "section_id": section.id,
        "location": fact.location.strip() or section.heading_path,
    }
    upsert_entry(
        session,
        version_id,
        key,
        fact.kind,
        fact.topic.strip(),
        fact.statement.strip(),
        _details(fact),
        "from_document",
        [source],
        f"Found in {doc.file_name}",
    )
    entry = get_entry(session, version_id, key)
    if entry is not None:
        index_entry(session, entry, app="learner", learning_run_id=run_id)


def _details(fact: DocFactForm) -> dict:
    """Honest minimal details for document kinds."""
    if fact.kind == "rule":
        return {
            "rule_type": "required_note",
            "note_text": fact.statement.strip(),
            "applies_to_words": [fact.topic.strip()],
        }
    return {"tables": [], "columns": []}


def _fail(session: Session, doc: Document, message: str, say) -> None:
    """Mark the document failed with a plain message."""
    doc.status = "failed"
    doc.error = message
    doc.progress = 0
    session.flush()
    say("warning", f"Couldn't learn {doc.file_name}: {message}")


def run_job(info: JobInfo, ctx: StepContext) -> None:
    """The in-run job: extract one document's facts, then learn it."""
    doc = ctx.session.get(Document, (info.payload or {}).get("document_id"))
    if doc is None or doc.status in ("removed", "learned"):
        return
    try:
        extract_document(
            ctx.session, doc, say=ctx.say, version_id=ctx.version_id, run_id=ctx.run_id
        )
    except SpendingPaused:
        raise
    except Exception as err:  # noqa: BLE001 (the worker retries first; see below)
        # The worker retries a failed job twice more. Only on the last try
        # does the document itself fail, keeping what earlier sections wrote.
        if info.attempts >= 3:
            message = err.message if isinstance(err, AiError) else "Something went wrong."
            _fail(ctx.session, doc, message, ctx.say)
            return
        raise


def compare_run(
    session: Session, version_id: int, document_ids: list[int], *, say, run_id: int | None = None
) -> list[str]:
    """Mark conflicting facts over shared topics; returns the conflict topics."""
    facts = (
        session.scalars(
            select(DocFact).where(DocFact.document_id.in_(document_ids), DocFact.status == "ok")
        ).all()
        if document_ids
        else []
    )
    groups: dict[str, list[DocFact]] = {}
    for fact in facts:
        groups.setdefault(normalize_text(fact.topic).lower(), []).append(fact)
    if groups and document_ids:
        topics = {fact.topic for fact in facts}
        lowered = {topic.lower() for topic in topics}
        prior = session.scalars(
            select(DocFact)
            .join(Document, DocFact.document_id == Document.id)
            .where(
                or_(
                    DocFact.topic.in_(topics),
                    func.lower(DocFact.topic).in_(lowered),
                ),
                DocFact.status == "ok",
                Document.status != "removed",
                DocFact.document_id.not_in(document_ids),
            )
            .order_by(DocFact.id)
        ).all()
        for fact in prior:
            groups.setdefault(normalize_text(fact.topic).lower(), []).append(fact)
    conflicts: list[str] = []
    for topic, group in groups.items():
        statements = {normalize_text(fact.statement) for fact in group}
        if len(statements) < 2:
            continue
        if _agree(topic, [fact.statement for fact in group], run_id):
            continue
        for fact in group:
            fact.status = "conflicting"
            _mark_entry_conflicting(session, version_id, fact)
        label = group[0].topic.strip()
        conflicts.append(label)
        say("warning", f"Conflict in {label}: the documents disagree.")
    session.flush()
    return conflicts


def _agree(topic: str, statements: list[str], run_id: int | None) -> bool:
    """Code says same when the words match; the AI judges the rest."""
    form = get_ai().run(
        COMPARE_JOB,
        {"topic": topic, "statements": statements},
        CompareFactsForm,
        app="learner",
        learning_run_id=run_id,
    )
    return form.agree


def _mark_entry_conflicting(session: Session, version_id: int, fact: DocFact) -> None:
    """Conflicting entries show it, unless you already confirmed them."""
    key = f"doc.{fact.kind}.{slug(fact.topic)}.{fact.document_id}"
    entry = get_entry(session, version_id, key)
    if entry is None or entry.confidence == "confirmed":
        return
    entry.confidence = "conflicting"
    session.flush()


def finish_step(ctx: StepContext) -> None:
    """Compare this run's facts, then report what was learned."""
    run = ctx.session.get(LearningRun, ctx.run_id)
    document_ids = []
    if run is not None:
        try:
            jobs = run.progress["steps"][STEP_NAME]["jobs"]
        except (KeyError, TypeError):
            jobs = []
        for job_id in jobs:
            job = ctx.session.get(Job, job_id)
            if job is not None and (job.payload or {}).get("document_id"):
                document_ids.append(job.payload["document_id"])
    conflicts = compare_run(
        ctx.session, ctx.version_id, document_ids, say=ctx.say, run_id=ctx.run_id
    )
    if conflicts:
        word = "topic" if len(conflicts) == 1 else "topics"
        ctx.say("found", f"{len(conflicts)} conflicting {word} to review.")
    else:
        ctx.say("found", "No conflicts between the documents.")


DOC_FACTS_STEP = Step(
    name=STEP_NAME,
    title="Pull facts out of the documents",
    job_kind=EXTRACT_JOB,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="No new document facts to pull, so I skipped this step.",
)

register_step(DOC_FACTS_STEP)
register_step_handler(STEP_NAME)
