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
