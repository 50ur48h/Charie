"""The database itself guards meaning: cascades, single published version."""

import pytest
from sqlalchemy.exc import IntegrityError

from charie.shared.tables.chat import Chat, Message, NotebookItem
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.learning import Job
from charie.shared.tables.sources import Document, DocumentSection
from charie.shared.tables.usage import AiCall


def test_deleting_a_chat_deletes_messages_and_notebook(db_session):
    chat = Chat()
    db_session.add(chat)
    db_session.commit()
    message = Message(chat_id=chat.id, role="user", text_="Hi.")
    db_session.add(message)
    db_session.commit()
    db_session.add(
        NotebookItem(
            message_id=message.id,
            chat_id=chat.id,
            seq=1,
            round=1,
            label="n1",
            kind="number",
            description="A number.",
            value={"number": "3"},
        )
    )
    db_session.commit()
    db_session.delete(chat)
    db_session.commit()
    assert db_session.query(Message).count() == 0
    assert db_session.query(NotebookItem).count() == 0


def test_deleting_a_chat_keeps_ai_calls(db_session):
    chat = Chat()
    db_session.add(chat)
    db_session.commit()
    message = Message(chat_id=chat.id, role="user", text_="Hi.")
    db_session.add(message)
    db_session.commit()
    db_session.add(
        AiCall(
            app="chat",
            job="answer",
            provider="meta",
            model="m1",
            message_id=message.id,
        )
    )
    db_session.commit()
    db_session.delete(chat)
    db_session.commit()
    row = db_session.query(AiCall).one()
    assert row.message_id is None


def test_only_one_published_version(db_session):
    db_session.add(KbVersion(number=1, status="published", made_by="first_learning"))
    db_session.commit()
    db_session.add(KbVersion(number=2, status="published", made_by="refresh"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_entry_key_unique_per_version(db_session):
    version = KbVersion(number=1, status="draft", made_by="first_learning")
    db_session.add(version)
    db_session.commit()
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="metric.net_sales",
            kind="metric",
            title="Net sales",
            meaning="Sales minus refunds.",
            confidence="checked",
        )
    )
    db_session.commit()
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="metric.net_sales",
            kind="metric",
            title="Net sales again",
            meaning="Same key twice.",
            confidence="checked",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_status_check_refuses_unknown_value(db_session):
    db_session.add(Job(kind="read_document", status="stuck"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_search_text_is_filled(db_session):
    document = Document(file_name="guide.pdf", file_type="pdf", size_bytes=12, sha256="abc")
    db_session.add(document)
    db_session.commit()
    db_session.add(
        DocumentSection(
            document_id=document.id,
            position=1,
            heading_path="Refunds",
            text_="Refunds over $50 need a note.",
            note="Refund rule",
        )
    )
    db_session.commit()
    row = db_session.query(DocumentSection).one()
    assert "refund" in row.search_text.lower()
