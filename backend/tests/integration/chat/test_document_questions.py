"""The documents questions on the practice database (P10.8 Task 4).

Laptop-only: needs the practice database and the recorded AI replies.
Recording costs under $1: run `AI_REPLAY=record uv run pytest <this file>`
once with the owner's yes, then replay. Without cassettes it fails by
design, like the new-kind questions.

The seeded sections use the repository fixture documents' own sentences
(P08.7), so a recorded quote can always match word for word. One known
risk: documents-002 wants "Dec 2025" in a kept quote, but no fixture
sentence names December; the recording run will show whether that case
needs a fixture or question change.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest

from charie.chat.analyst.helpers.documents import run_document_task
from charie.chat.analyst.helpers.tasks import starter_tasks
from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.understand import understand
from charie.shared.crypto import encrypt_text
from charie.shared.settings import set_setting
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.sources import DataSource, Document, DocumentSection
from tests.integration.chat import test_data_helper as shop
from tests.questions.format import load_questions

CASES = [
    "documents-001",
    "documents-002",
    "documents-003",
    "documents-004",
    "documents-005",
]

PUBLIC = Path(__file__).resolve().parents[2] / "questions" / "public.yaml"

FINANCE = "Finance definitions 2025.docx"
POLICY = "Conflicting policy 2025.docx"


def _seed_documents(db_session) -> int:
    """A published version with the fixture documents' own sentences."""
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()

    def _document(name: str, sections: list[tuple[str, str]]) -> None:
        row = Document(
            file_name=name, file_type="docx", size_bytes=10, sha256=name, status="learned"
        )
        row.progress = 100
        db_session.add(row)
        db_session.flush()
        for position, (heading, text) in enumerate(sections):
            db_session.add(
                DocumentSection(
                    document_id=row.id,
                    position=position,
                    heading_path=heading,
                    text_=text,
                    page_from=1,
                    page_to=1,
                )
            )

    _document(
        FINANCE,
        [
            (
                "Definitions",
                "Net sales means total orders minus refunds. "
                "Net sales equals total orders minus refunds. "
                "Net sales were $1.2M in 2025.",
            ),
            ("Checkout", "Use code MEGA0926 at checkout."),
            ("Prices", "| Margherita | 18.00 |"),
        ],
    )
    _document(
        POLICY,
        [
            (
                "Policy",
                "Net sales means gross profit. Net sales were $1.5M in 2025.",
            )
        ],
    )
    raw = os.environ["PRACTICE_DB_URL"]
    target = urlparse(raw if "://" in raw else f"postgresql://{raw}")
    db_session.add(
        DataSource(
            kind="postgres",
            name="Practice database",
            host=target.hostname or "localhost",
            port=target.port or 5432,
            database=(target.path or "/shop").lstrip("/"),
            username=target.username or "owner",
            password_encrypted=encrypt_text(target.password or ""),
            status="connected",
            data_through=datetime(2025, 12, 31, tzinfo=UTC),
        )
    )
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()
    return version.id


def _by_id(case_id: str):
    for question in load_questions(str(PUBLIC), "public"):
        if question.id == case_id:
            return question
    raise AssertionError(f"no question {case_id} in public.yaml")


@pytest.mark.practice_db
@pytest.mark.live_ai
@pytest.mark.parametrize("case_id", CASES)
def test_documents_question(db_session, case_id) -> None:
    """Each documents question finds quotes; every must_say is quoted."""
    version_id = _seed_documents(db_session)
    question = _by_id(case_id)
    ctx = shop._ctx(db_session, version_id, question=question.question)
    understand(ctx)
    kb = KbView.load(db_session, version_id)
    for task in starter_tasks(ctx.understanding, kb.titles()):
        if task.kind == "documents":
            run_document_task(task, ctx)
    book = shop._notebook(db_session, ctx)
    kept = [item.value["text"] for item in book.items() if item.kind == "quote"]
    assert kept, f"{case_id}: the notebook has no quotes"
    for phrase in question.expect.must_say:
        assert any(phrase in quote for quote in kept), f"{case_id}: no kept quote says {phrase!r}"
