"""Every table matches architecture 05 (column names, checks, indexes)."""

from sqlalchemy import CheckConstraint

from charie.shared import tables  # noqa: F401
from charie.shared.db import Base

EXPECTED_TABLES = {
    "settings": {"key", "value", "updated_at"},
    "data_sources": {
        "id",
        "kind",
        "name",
        "host",
        "port",
        "database",
        "username",
        "password_encrypted",
        "status",
        "read_only_ok",
        "data_through",
        "checked_at",
        "details",
    },
    "documents": {
        "id",
        "file_name",
        "file_type",
        "size_bytes",
        "sha256",
        "status",
        "progress",
        "pages",
        "unreadable_pages",
        "fact_count",
        "error",
        "uploaded_at",
        "learned_at",
    },
    "document_files": {"document_id", "content"},
    "document_sections": {
        "id",
        "document_id",
        "position",
        "heading_path",
        "text",
        "page_from",
        "page_to",
        "note",
        "embedding",
        "search_text",
    },
    "doc_facts": {
        "id",
        "document_id",
        "section_id",
        "kind",
        "topic",
        "statement",
        "quote",
        "location",
        "status",
    },
    "owner_notes": {"id", "text", "saved_at", "sorted_at"},
    "kb_versions": {
        "id",
        "number",
        "status",
        "made_by",
        "created_at",
        "published_at",
        "summary",
        "readiness",
    },
    "kb_entries": {
        "id",
        "version_id",
        "key",
        "kind",
        "title",
        "meaning",
        "details",
        "confidence",
        "sources",
        "search_text",
        "embedding",
        "updated_at",
    },
    "kb_changes": {
        "id",
        "version_id",
        "key",
        "change",
        "before",
        "after",
        "reason",
        "is_big",
    },
    "owner_questions": {
        "id",
        "status",
        "rank",
        "importance",
        "topic",
        "title",
        "body",
        "evidence",
        "options",
        "default_option",
        "answer",
        "affects",
        "source",
        "created_at",
        "answered_at",
    },
    "learner_todos": {
        "id",
        "kind",
        "text",
        "details",
        "status",
        "result",
        "created_at",
        "done_at",
    },
    "learning_runs": {
        "id",
        "kind",
        "reason",
        "status",
        "step",
        "progress",
        "version_id",
        "cost_usd",
        "summary",
        "started_at",
        "finished_at",
    },
    "learning_events": {"id", "run_id", "at", "step", "kind", "message", "details"},
    "jobs": {
        "id",
        "run_id",
        "kind",
        "payload",
        "status",
        "priority",
        "run_after",
        "attempts",
        "locked_at",
        "heartbeat_at",
        "worker",
        "error",
        "created_at",
        "finished_at",
    },
    "chats": {"id", "title", "context", "created_at", "updated_at"},
    "messages": {
        "id",
        "chat_id",
        "role",
        "text",
        "answer",
        "status",
        "mode",
        "kb_version_id",
        "data_through",
        "seconds",
        "steps",
        "queries",
        "documents",
        "cost_usd",
        "feedback",
        "feedback_note",
        "started_at",
        "finished_at",
    },
    "thinking_events": {
        "id",
        "message_id",
        "seq",
        "at",
        "kind",
        "status",
        "title",
        "body",
        "details",
    },
    "notebook_items": {
        "id",
        "message_id",
        "chat_id",
        "seq",
        "round",
        "label",
        "kind",
        "description",
        "value",
        "status",
        "replaced_by",
        "replace_reason",
        "proof",
    },
    "query_runs": {
        "id",
        "message_id",
        "learning_run_id",
        "purpose",
        "recipe_key",
        "way",
        "sql_text",
        "check_report",
        "status",
        "row_count",
        "duration_ms",
        "error",
        "created_at",
    },
    "memories": {"id", "text", "kind", "source_chat_id", "active", "created_at"},
    "ai_calls": {
        "id",
        "at",
        "app",
        "job",
        "provider",
        "model",
        "reasoning_effort",
        "prompt_tokens",
        "cached_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "cost_usd",
        "duration_ms",
        "status",
        "message_id",
        "learning_run_id",
        "error",
    },
}


def test_twenty_two_tables_exist():
    assert set(Base.metadata.tables) == set(EXPECTED_TABLES)


def test_columns_match_05():
    for name, columns in EXPECTED_TABLES.items():
        found = {column.name for column in Base.metadata.tables[name].columns}
        assert found == columns, name


def test_status_checks_list_05_values():

    documents = Base.metadata.tables["documents"]
    checks = [
        str(c.sqltext)
        for c in documents.constraints
        if isinstance(c, CheckConstraint) and "status" in str(c.sqltext)
    ]
    assert len(checks) == 1
    for value in ("new", "reading", "learned", "failed", "removed"):
        assert f"'{value}'" in checks[0]


def test_one_published_version_index():
    versions = Base.metadata.tables["kb_versions"]
    partial = [
        index
        for index in versions.indexes
        if index.unique and "published" in str(index.dialect_options["postgresql"]["where"])
    ]
    assert len(partial) == 1


def _index_options(table_name, index_name):
    table = Base.metadata.tables[table_name]
    for index in table.indexes:
        if index.name == index_name:
            options = index.dialect_options["postgresql"]
            return options.get("using"), options.get("ops")
    raise AssertionError(f"missing index {index_name} on {table_name}")


def test_document_sections_indexes():
    using, ops = _index_options("document_sections", "ix_document_sections_embedding")
    assert using == "hnsw"
    assert ops == {"embedding": "vector_cosine_ops"}
    using, _ = _index_options("document_sections", "ix_document_sections_search_text")
    assert using == "gin"
    using, ops = _index_options("document_sections", "ix_document_sections_heading_path")
    assert using == "gin"
    assert ops == {"heading_path": "gin_trgm_ops"}
    using, ops = _index_options("document_sections", "ix_document_sections_note")
    assert using == "gin"
    assert ops == {"note": "gin_trgm_ops"}


def test_every_foreign_key_has_an_index():
    for name, table in Base.metadata.tables.items():
        indexed = {column.name for index in table.indexes for column in index.columns}
        for column in table.columns:
            # A primary key is indexed by Postgres itself; every other
            # foreign-key column needs an explicit index.
            if column.foreign_keys and not column.primary_key:
                assert column.name in indexed, f"{name}.{column.name}"
