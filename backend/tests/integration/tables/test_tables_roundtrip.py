"""A row can be written and read in every table of the throwaway database."""

import secrets
from urllib.parse import urlparse, urlunparse

from alembic import command
from sqlalchemy import create_engine, inspect, text

from charie.shared.config import get_settings
from charie.shared.db import Base, psycopg_url
from charie.shared.tables.chat import Chat, Memory, Message, NotebookItem, QueryRun, ThinkingEvent
from charie.shared.tables.knowledge import KbChange, KbEntry, KbVersion
from charie.shared.tables.learning import Job, LearningEvent, LearningRun
from charie.shared.tables.questions import LearnerTodo, OwnerQuestion
from charie.shared.tables.settings import Setting
from charie.shared.tables.sources import (
    DataSource,
    DocFact,
    Document,
    DocumentFile,
    DocumentSection,
    OwnerNote,
)
from charie.shared.tables.usage import AiCall
from tests.conftest import alembic_config


def _source(db_session):
    row = DataSource(
        kind="postgres",
        name="practice",
        host="localhost",
        port=5432,
        database="practice",
        username="charie_readonly",
        password_encrypted=" Fernet-sealed ",
        status="connected",
    )
    db_session.add(row)
    db_session.commit()
    return row


def _document(db_session):
    row = Document(file_name="guide.pdf", file_type="pdf", size_bytes=12, sha256="abc")
    db_session.add(row)
    db_session.commit()
    return row


def _section(db_session, document):
    row = DocumentSection(
        document_id=document.id,
        position=1,
        heading_path="Refunds > Exceptions",
        text_="Refunds over $50 need a note.",
        note="Refund rule",
    )
    db_session.add(row)
    db_session.commit()
    return row


def _version(db_session, number=1, status="draft"):
    row = KbVersion(number=number, status=status, made_by="first_learning")
    db_session.add(row)
    db_session.commit()
    return row


def _chat(db_session):
    row = Chat()
    db_session.add(row)
    db_session.commit()
    return row


def _message(db_session, chat):
    row = Message(chat_id=chat.id, role="user", text_="What were net sales?")
    db_session.add(row)
    db_session.commit()
    return row


def _run(db_session):
    row = LearningRun(kind="first", reason="3 new documents")
    db_session.add(row)
    db_session.commit()
    return row


def test_setting_round_trip(db_session):
    db_session.add(Setting(key="theme", value="sage"))
    db_session.commit()
    row = db_session.get(Setting, "theme")
    assert row.value == "sage"
    assert row.updated_at is not None


def test_data_source_round_trip(db_session):
    row = _source(db_session)
    assert row.details == {}
    assert row.read_only_ok is False
    assert row.data_through is None


def test_document_round_trip(db_session):
    row = _document(db_session)
    assert row.status == "new"
    assert (row.progress, row.pages, row.unreadable_pages, row.fact_count) == (0, 0, 0, 0)
    assert row.uploaded_at is not None
    assert row.learned_at is None


def test_document_file_round_trip(db_session):
    document = _document(db_session)
    db_session.add(DocumentFile(document_id=document.id, content=b"%PDF-fake"))
    db_session.commit()
    row = db_session.get(DocumentFile, document.id)
    assert row.content == b"%PDF-fake"


def test_document_section_round_trip(db_session):
    row = _section(db_session, _document(db_session))
    assert "refund" in row.search_text.lower()
    assert row.embedding is None


def test_doc_fact_round_trip(db_session):
    document = _document(db_session)
    section = _section(db_session, document)
    db_session.add(
        DocFact(
            document_id=document.id,
            section_id=section.id,
            kind="rule",
            topic="refunds",
            statement="Refunds over $50 need a note.",
            quote="Refunds over $50 need a note.",
        )
    )
    db_session.commit()
    row = db_session.query(DocFact).one()
    assert row.status == "ok"
    assert row.location is None


def test_owner_note_round_trip(db_session):
    db_session.add(OwnerNote(text_="Leave out test restaurants."))
    db_session.commit()
    row = db_session.query(OwnerNote).one()
    assert row.saved_at is not None
    assert row.sorted_at is None


def test_kb_version_round_trip(db_session):
    row = _version(db_session)
    assert row.status == "draft"
    assert row.summary == {}
    assert row.readiness is None


def test_kb_entry_round_trip(db_session):
    version = _version(db_session)
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="metric.net_sales",
            kind="metric",
            title="Net sales",
            meaning="Sales minus refunds, in US dollars.",
            confidence="checked",
        )
    )
    db_session.commit()
    row = db_session.query(KbEntry).one()
    assert row.details == {}
    assert row.sources == []
    assert "sale" in row.search_text.lower()
    assert row.updated_at is not None


def test_kb_change_round_trip(db_session):
    version = _version(db_session)
    db_session.add(KbChange(version_id=version.id, key="metric.net_sales", change="added"))
    db_session.commit()
    row = db_session.query(KbChange).one()
    assert row.before is None
    assert row.after is None
    assert row.is_big is False


def test_owner_question_round_trip(db_session):
    db_session.add(
        OwnerQuestion(
            topic="refunds",
            title="Which refunds count?",
            body="Do staff refunds count as sales?",
            source="learning",
        )
    )
    db_session.commit()
    row = db_session.query(OwnerQuestion).one()
    assert row.status == "waiting"
    assert (row.rank, row.importance) == (0, 0)
    assert row.evidence == {}
    assert row.options == []
    assert row.affects == []
    assert row.answer is None


def test_learner_todo_round_trip(db_session):
    db_session.add(LearnerTodo(kind="correction", text_="Fix net sales."))
    db_session.commit()
    row = db_session.query(LearnerTodo).one()
    assert row.status == "open"
    assert row.details == {}


def test_learning_run_round_trip(db_session):
    row = _run(db_session)
    assert row.status == "running"
    assert row.progress == {}
    assert float(row.cost_usd) == 0
    assert row.started_at is not None


def test_learning_event_round_trip(db_session):
    run = _run(db_session)
    db_session.add(LearningEvent(run_id=run.id, kind="found", message="Found 3 facts."))
    db_session.commit()
    row = db_session.query(LearningEvent).one()
    assert row.at is not None
    assert row.details == {}


def test_job_round_trip(db_session):
    db_session.add(Job(kind="read_document"))
    db_session.commit()
    row = db_session.query(Job).one()
    assert row.status == "queued"
    assert row.priority == 100
    assert row.attempts == 0
    assert row.run_after is not None


def test_chat_round_trip(db_session):
    row = _chat(db_session)
    assert row.title == "New chat"
    assert row.context == {}


def test_message_round_trip(db_session):
    row = _message(db_session, _chat(db_session))
    assert row.status == "thinking"
    assert row.mode == "thinking"
    assert (row.seconds, row.steps, row.queries, row.documents) == (0, 0, 0, 0)
    assert row.answer is None


def test_thinking_event_round_trip(db_session):
    message = _message(db_session, _chat(db_session))
    db_session.add(
        ThinkingEvent(message_id=message.id, seq=1, kind="step", title="Reading", body="Reading.")
    )
    db_session.commit()
    row = db_session.query(ThinkingEvent).one()
    assert row.status == "running"
    assert row.at is not None


def test_notebook_item_round_trip(db_session):
    chat = _chat(db_session)
    message = _message(db_session, chat)
    db_session.add(
        NotebookItem(
            message_id=message.id,
            chat_id=chat.id,
            seq=1,
            round=1,
            label="n1",
            kind="number",
            description="Net sales in December.",
            value={"number": "1420000"},
        )
    )
    db_session.commit()
    row = db_session.query(NotebookItem).one()
    assert row.status == "ok"
    assert row.proof == {}


def test_query_run_round_trip(db_session):
    message = _message(db_session, _chat(db_session))
    db_session.add(QueryRun(message_id=message.id, purpose="Net sales test.", status="ok"))
    db_session.commit()
    row = db_session.query(QueryRun).one()
    assert row.check_report == {}
    assert (row.row_count, row.duration_ms) == (0, 0)


def test_memory_round_trip(db_session):
    db_session.add(Memory(text_="Austin means downtown.", kind="meaning"))
    db_session.commit()
    row = db_session.query(Memory).one()
    assert row.active is True
    assert row.source_chat_id is None


def test_ai_call_round_trip(db_session):
    db_session.add(AiCall(app="chat", job="name_chat", provider="meta", model="m1"))
    db_session.commit()
    row = db_session.query(AiCall).one()
    assert row.status == "ok"
    assert (row.prompt_tokens, row.reasoning_tokens) == (0, 0)
    assert row.at is not None


def test_database_matches_models(db, test_db_url):
    engine = create_engine(test_db_url)
    try:
        found = set(inspect(engine).get_table_names()) - {"alembic_version"}
        assert found == set(Base.metadata.tables)
        for name in Base.metadata.tables:
            columns = {c["name"] for c in inspect(engine).get_columns(name)}
            assert columns == {c.name for c in Base.metadata.tables[name].columns}, name
    finally:
        engine.dispose()


def test_downgrade_removes_everything(test_db_url):
    parts = urlparse(psycopg_url(get_settings().database_url or ""))
    server_url = urlunparse(parts._replace(path="/postgres"))
    name = f"charie_test_{secrets.token_hex(4)}"
    maker = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with maker.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    maker.dispose()
    url = urlunparse(parts._replace(path=f"/{name}"))
    try:
        command.upgrade(alembic_config(url), "head")
        command.downgrade(alembic_config(url), "base")
        engine = create_engine(url, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                tables = conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
                    )
                ).all()
                assert tables == []
                extensions = conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')")
                ).all()
                assert extensions == []
        finally:
            engine.dispose()
    finally:
        dropper = create_engine(server_url, isolation_level="AUTOCOMMIT")
        with dropper.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        dropper.dispose()
