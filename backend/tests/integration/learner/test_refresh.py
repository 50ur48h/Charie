"""P08.8 refresh: selection, invalidation and resume (fakes only, no network)."""

import pytest
from sqlalchemy import select

from charie.learner import runs
from charie.learner.steps import doc_facts, documents, owner_notes, refresh
from charie.learner.steps.base import StepContext
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge.store import get_entry
from charie.shared.knowledge.versions import get_or_create_draft
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import LearnerTodo
from charie.shared.tables.sources import (
    DocFact,
    Document,
    DocumentFile,
    DocumentSection,
    OwnerNote,
)


def _say():
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    return say, said


def _ctx(session, run_id: int, version_id: int):
    say, said = _say()
    return (
        StepContext(
            session=session,
            run_id=run_id,
            version_id=version_id,
            source=None,
            connector=None,
            strict_mode=False,
            settings={},
            say=say,
        ),
        said,
    )


def _add_md_doc(session, name: str = "guide.md", status: str = "new") -> int:
    row = Document(file_name=name, file_type="md", size_bytes=10, sha256=name, status=status)
    row.progress = 100
    session.add(row)
    session.flush()
    session.add(DocumentFile(document_id=row.id, content=b"# Guide\n\nNet sales means total.\n"))
    session.flush()
    return row.id


def _seed_learned_doc(session, name: str = "guide.md") -> int:
    doc_id = _add_md_doc(session, name, status="learned")
    session.add(
        DocumentSection(
            document_id=doc_id, position=0, heading_path="Guide", text_="Net sales means total."
        )
    )
    session.flush()
    return doc_id


def _begin(session, reason: str | None = None):
    run = refresh.begin(session, kind="refresh", reason=reason)
    session.commit()
    return run


def _drive_to_done(db_session, monkeypatch, run_id: int):
    """Run every queued job through the real step handler until the run ends."""
    from decimal import Decimal

    from charie.learner.steps import doc_facts, document_index
    from charie.shared.ai.client import AiClient
    from charie.shared.ai.cost_log import MemoryCostLog
    from charie.shared.ai.fake import FakeAi
    from charie.shared.search import search as search_mod
    from charie.shared.search.embeddings import EmbeddingResult
    from charie.shared.tables.learning import Job

    class _EmbedStub:
        def embed_texts(self, texts, **kwargs):
            return EmbeddingResult(
                vectors=[[1.0] + [0.0] * 1535 for _ in texts],
                prompt_tokens=len(texts),
                cost_usd=Decimal("0"),
            )

    fake = (
        FakeAi()
        .reply(
            "extract_doc_facts",
            {
                "facts": [
                    {
                        "kind": "definition",
                        "topic": "Net sales",
                        "statement": "Net sales means total.",
                        "quote": "Net sales means total.",
                        "location": "Guide",
                    }
                ]
            },
        )
        .reply("note_section", {"note": "Net sales means total."})
    )
    fake_client = lambda: AiClient(  # noqa: E731
        provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None
    )
    monkeypatch.setattr(doc_facts, "get_ai", fake_client)
    monkeypatch.setattr(document_index, "get_ai", fake_client)
    monkeypatch.setattr(search_mod, "embeddings", _EmbedStub())
    monkeypatch.setattr(document_index, "embeddings", _EmbedStub())
    for _ in range(30):
        db_session.expire_all()
        run = db_session.get(LearningRun, run_id)
        if run is None or run.status != "running" or run.step is None:
            return
        for job_id in run.progress["steps"][run.step]["jobs"]:
            job = db_session.get(Job, job_id)
            if job is not None and job.status in ("queued", "running"):
                info = JobInfo(
                    id=job.id, kind=job.kind, payload=dict(job.payload or {}), run_id=run_id
                )
                runs.run_step_job(info)
    raise AssertionError("the refresh run did not finish")


def test_unchanged_no_calls(db_session, monkeypatch) -> None:
    doc_id = _seed_learned_doc(db_session)
    db_session.commit()
    first = _begin(db_session)
    assert first.status == "done"
    db_session.commit()
    consumed = refresh.last_consumed(db_session)
    assert consumed is not None
    assert consumed["documents"] == {str(doc_id): "guide.md"}
    second = _begin(db_session)
    ctx, _said = _ctx(db_session, second.id, second.version_id)
    assert documents.make_jobs(ctx) == []
    assert doc_facts.make_jobs(ctx) == []
    assert owner_notes.make_jobs(ctx) == []
    db_session.commit()


def test_changed_only(db_session) -> None:
    old_id = _seed_learned_doc(db_session, "old.md")
    new_id = _add_md_doc(db_session, "new.md", status="new")
    db_session.add(OwnerNote(text_="Never use the test table."))
    db_session.commit()
    assert refresh.last_consumed(db_session) is None
    run = _begin(db_session)
    scope = refresh.scope_for(db_session, run.id)
    assert scope is not None
    assert scope["documents"] == [new_id]
    assert old_id not in scope["documents"]
    assert scope["notes_id"] is not None
    ctx, _said = _ctx(db_session, run.id, run.version_id)
    assert [job["document_id"] for job in documents.make_jobs(ctx)] == [new_id]
    assert [job["document_id"] for job in doc_facts.make_jobs(ctx)] == []
    assert owner_notes.make_jobs(ctx) == [{"owner_notes_id": scope["notes_id"]}]


def test_removal_invalidates(db_session) -> None:
    doc_id = _seed_learned_doc(db_session, "gone.md")
    version = get_or_create_draft(db_session, "first_learning")
    fact = DocFact(
        document_id=doc_id,
        section_id=db_session.scalar(select(DocumentSection.id)),
        kind="definition",
        topic="Net sales",
        statement="Net sales means total.",
        quote="Net sales means total.",
        location="Guide",
        status="ok",
    )
    db_session.add(fact)
    db_session.flush()
    from charie.shared.knowledge.store import upsert_entry

    upsert_entry(
        db_session,
        version.id,
        "doc.definition.net_sales.1",
        "definition",
        "Net sales",
        "Net sales means total.",
        {"tables": [], "columns": []},
        "from_document",
        [
            {
                "type": "document",
                "quote": "Net sales means total.",
                "document": "gone.md",
                "section_id": fact.section_id,
            }
        ],
        "Found in gone.md",
    )
    db_session.commit()
    first = _begin(db_session)
    runs.advance_run(db_session, first.id)
    db_session.commit()
    row = db_session.get(Document, doc_id)
    row.status = "removed"
    db_session.commit()
    second = _begin(db_session)
    facts = db_session.scalars(select(DocFact).where(DocFact.document_id == doc_id)).all()
    assert facts and all(fact.status == "needs_checking" for fact in facts)
    todos = db_session.scalars(select(LearnerTodo).where(LearnerTodo.status == "open")).all()
    assert len(todos) == 1 and todos[0].kind == "correction"
    entry = get_entry(db_session, second.version_id, "doc.definition.net_sales.1")
    assert entry is not None and entry.meaning == "Net sales means total."
    db_session.commit()


def test_change_during_run(db_session, monkeypatch) -> None:
    first_id = _add_md_doc(db_session, "first.md", status="new")
    db_session.commit()
    run = _begin(db_session)
    saved = refresh.last_consumed(db_session)
    assert saved is None
    late_id = _add_md_doc(db_session, "late.md", status="new")
    db_session.commit()
    _drive_to_done(db_session, monkeypatch, run.id)
    db_session.expire_all()
    done = db_session.get(LearningRun, run.id)
    assert done is not None and done.status == "done"
    consumed = refresh.last_consumed(db_session)
    assert consumed is not None
    assert str(first_id) in consumed["documents"]
    assert str(late_id) not in consumed["documents"]
    pending = refresh.pending(db_session)
    assert late_id in pending["documents"]
    assert db_session.get(Document, late_id).status == "new"


def test_refresh_endpoint_starts_selective_run(db_session, learner_client) -> None:
    from tests.conftest import log_in

    _seed_learned_doc(db_session, "old.md")
    new_id = _add_md_doc(db_session, "new.md", status="new")
    db_session.commit()
    log_in(learner_client)
    response = learner_client.post("/api/learning/refresh", json={"reason": "new file"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "refresh" and body["status"] == "running"
    db_session.expire_all()
    run = db_session.get(LearningRun, body["id"])
    assert run is not None
    assert run.progress["refresh"]["documents"] == [new_id]
    assert run.progress["refresh"]["notes_id"] is None
    queued = run.progress["steps"]["documents"]["jobs"]
    assert len(queued) == 1


def test_failure_keeps_published(db_session, monkeypatch) -> None:
    from charie.shared.ai.client import AiClient
    from charie.shared.ai.cost_log import MemoryCostLog
    from charie.shared.ai.errors import AiError
    from charie.shared.ai.fake import FakeAi

    published = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(published)
    db_session.flush()
    db_session.add(
        KbEntry(
            version_id=published.id,
            key="rule.keep",
            kind="rule",
            title="Keep",
            meaning="Keep this always.",
            details={},
            confidence="confirmed",
            sources=[{"type": "owner_notes", "quote": "Keep this always."}],
        )
    )
    db_session.add(OwnerNote(text_="Keep this always."))
    db_session.commit()
    run = _begin(db_session)
    job_id = run.progress["steps"]["owner_notes"]["jobs"][0]
    monkeypatch.setattr(
        "charie.learner.steps.owner_notes.get_ai",
        lambda: AiClient(provider=FakeAi(), cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    info = JobInfo(
        id=job_id,
        kind="sort_owner_notes",
        payload={"owner_notes_id": db_session.scalar(select(OwnerNote.id)), "step": "owner_notes"},
        run_id=run.id,
        attempts=3,
    )
    with pytest.raises(AiError):
        runs.run_step_job(info)
    db_session.expire_all()
    failed = db_session.get(LearningRun, run.id)
    assert failed is not None and failed.status == "failed"
    assert refresh.last_consumed(db_session) is None
    published_now = db_session.scalar(select(KbVersion).where(KbVersion.status == "published"))
    assert published_now is not None and published_now.id == published.id
    kept = get_entry(db_session, published.id, "rule.keep")
    assert kept is not None and kept.meaning == "Keep this always."
