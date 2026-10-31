"""The documents API: list, upload, remove, retry (P08.2)."""

from sqlalchemy import select

from charie.shared.tables.learning import Job
from charie.shared.tables.sources import Document, DocumentFile
from tests.conftest import log_in

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n"


def _seed(session, **overrides):
    row = Document(file_name="a.pdf", file_type="pdf", **overrides)
    session.add(row)
    session.flush()
    session.add(DocumentFile(document_id=row.id, content=PDF))
    session.commit()
    return row.id


def test_upload_queues_reading(learner_client, db_session) -> None:
    log_in(learner_client)
    response = learner_client.post(
        "/api/documents", files={"file": ("a.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 201, response.text
    doc = response.json()["document"]
    assert doc["status"] == "new" and doc["pages"] is None and doc["progress"] is None
    jobs = db_session.scalars(select(Job).where(Job.kind == "read_document")).all()
    assert len(jobs) == 1 and jobs[0].payload["document_id"] == doc["id"]


def test_upload_same_content_returns_active(learner_client, db_session) -> None:
    log_in(learner_client)
    first = learner_client.post(
        "/api/documents", files={"file": ("a.pdf", PDF, "application/pdf")}
    ).json()["document"]
    second = learner_client.post(
        "/api/documents", files={"file": ("copy.pdf", PDF, "application/pdf")}
    )
    assert second.status_code == 200, second.text
    assert second.json()["document"]["id"] == first["id"]
    jobs = db_session.scalars(select(Job).where(Job.kind == "read_document")).all()
    assert len(jobs) == 1  # No duplicate reading work.


def test_list_hides_removed(learner_client, db_session) -> None:
    log_in(learner_client)
    db_session.add_all(
        [
            Document(
                file_name="old.pdf", file_type="pdf", size_bytes=3, sha256="gone", status="removed"
            ),
            Document(
                file_name="new.pdf", file_type="pdf", size_bytes=3, sha256="live", status="new"
            ),
        ]
    )
    db_session.commit()
    response = learner_client.get("/api/documents")
    assert response.status_code == 200, response.text
    names = [doc["file_name"] for doc in response.json()["documents"]]
    assert names == ["new.pdf"]


def test_rejects_too_big(learner_client, db_session) -> None:
    log_in(learner_client)
    big = b"%PDF" + b"0" * (50 * 1024 * 1024)
    response = learner_client.post(
        "/api/documents", files={"file": ("big.pdf", big, "application/pdf")}
    )
    assert response.status_code == 413, response.text
    assert db_session.query(Document).count() == 0  # Nothing saved.


def test_rejects_bad_type(learner_client, db_session) -> None:
    log_in(learner_client)
    response = learner_client.post(
        "/api/documents", files={"file": ("run.exe", b"MZ", "application/octet-stream")}
    )
    assert response.status_code == 400, response.text
    assert "can't be added" in response.json()["message"]
    assert db_session.query(Document).count() == 0


def test_remove_hides_document(learner_client, db_session) -> None:
    from charie.shared.tables.knowledge import KbVersion

    log_in(learner_client)
    doc_id = _seed(
        db_session, size_bytes=len(PDF), sha256="abc", status="failed", error="Unreadable."
    )
    response = learner_client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 204, response.text
    assert db_session.get(Document, doc_id).status == "removed"
    assert all(
        doc["id"] != doc_id for doc in learner_client.get("/api/documents").json()["documents"]
    )
    assert db_session.query(KbVersion).count() == 0  # Knowledge untouched.


def test_retry_failed_queues_reading(learner_client, db_session) -> None:
    from charie.shared.tables.knowledge import KbVersion

    log_in(learner_client)
    doc_id = _seed(
        db_session, size_bytes=len(PDF), sha256="abc", status="failed", error="Unreadable."
    )
    retry = learner_client.post(f"/api/documents/{doc_id}/retry")
    assert retry.status_code == 200, retry.text
    assert retry.json()["document"]["status"] == "new"
    jobs = db_session.scalars(select(Job).where(Job.kind == "read_document")).all()
    assert len(jobs) == 1 and jobs[0].payload["document_id"] == doc_id
    assert db_session.query(KbVersion).count() == 0  # Knowledge untouched.


def test_retry_learned_409s(learner_client, db_session) -> None:
    log_in(learner_client)
    doc_id = _seed(db_session, size_bytes=len(PDF), sha256="abc", status="learned")
    retry = learner_client.post(f"/api/documents/{doc_id}/retry")
    assert retry.status_code == 409, retry.text


def test_remove_missing_404s(learner_client) -> None:
    log_in(learner_client)
    response = learner_client.delete("/api/documents/999999")
    assert response.status_code == 404, response.text


def test_multipart_exception_documented(learner_client) -> None:
    """Uploads ride multipart, not JSON; JSON alone uploads nothing."""
    log_in(learner_client)
    multi = learner_client.post("/api/documents", files={"file": ("a.pdf", PDF, "application/pdf")})
    assert multi.status_code == 201, multi.text  # No 415: multipart is the exception.
    plain = learner_client.post("/api/documents", json={})
    assert plain.status_code == 400, plain.text  # JSON without a file part uploads nothing.


def test_retry_with_sections_resumes_index(learner_client, db_session, monkeypatch) -> None:
    """Retry after an index failure re-indexes; notes, vectors and hashes survive."""
    from decimal import Decimal

    from charie.learner.steps import document_index
    from charie.learner.steps.document_index import INDEX_JOB, content_hash, handle_index_document
    from charie.shared.ai.client import AiClient
    from charie.shared.ai.cost_log import MemoryCostLog
    from charie.shared.ai.fake import FakeAi
    from charie.shared.jobs.registry import JobInfo
    from charie.shared.search.embeddings import EmbeddingResult
    from charie.shared.tables.sources import DocumentSection

    log_in(learner_client)
    doc_id = _seed(db_session, size_bytes=len(PDF), sha256="abc", status="failed")
    done_text = "# Refunds\n\nFull refunds within 30 days.\n"
    pending_text = "# Shipping\n\nShips in 2 days.\n"
    db_session.add_all(
        [
            DocumentSection(
                document_id=doc_id,
                position=0,
                heading_path="Refunds",
                text_=done_text,
                note="Refund policy: 30 days.",
                embedding=[1.0] + [0.0] * 1535,
                content_hash=content_hash("Refunds", done_text),
            ),
            DocumentSection(
                document_id=doc_id, position=1, heading_path="Shipping", text_=pending_text
            ),
        ]
    )
    db_session.commit()

    retry = learner_client.post(f"/api/documents/{doc_id}/retry")
    assert retry.status_code == 200, retry.text
    assert retry.json()["document"]["status"] == "reading"
    kinds = [job.kind for job in db_session.scalars(select(Job))]
    assert kinds == ["index_document"]  # No re-read: sections are kept.

    # One reply: only the pending section may spend an AI call.
    fake = FakeAi().reply("note_section", {"note": "Shipping: 2 days."})
    monkeypatch.setattr(
        document_index,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )

    class StubEmbed:
        def embed_texts(self, texts, **kwargs):
            return EmbeddingResult(
                vectors=[[1.0] + [0.0] * 1535 for _ in texts],
                prompt_tokens=0,
                cost_usd=Decimal("0"),
            )

    monkeypatch.setattr(document_index, "embeddings", StubEmbed())
    handle_index_document(JobInfo(id=1, kind=INDEX_JOB, payload={"document_id": doc_id}))
    db_session.expire_all()
    assert [call[0] for call in fake.calls] == ["note_section"]  # Only the pending one.
    rows = db_session.scalars(
        select(DocumentSection)
        .where(DocumentSection.document_id == doc_id)
        .order_by(DocumentSection.position)
    ).all()
    assert [section.note for section in rows] == ["Refund policy: 30 days.", "Shipping: 2 days."]
    assert rows[0].note == "Refund policy: 30 days."  # Untouched.
    assert rows[0].embedding == [1.0] + [0.0] * 1535  # Untouched.
    assert all(len(section.embedding) == 1536 for section in rows)
    doc = db_session.get(Document, doc_id)
    assert (doc.status, doc.progress) == ("reading", 100)
