"""Platform database schema — the tables from architecture Part 10.1."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from charie.db.base import ROLES, Base, CreatedAt, OrgId, UuidPk

# Imported for its side effect: the table has to be on Base.metadata or Alembic autogenerate...
from charie.db.security_events import SecurityEvent

__all__ = [
    "CARD_TEXT_CONFIGURATION",
    "CHUNK_TEXT_CONFIGURATION",
    "COLUMN_POLICIES",
    "CONFIDENCE_LEVELS",
    "DATA_SOURCE_ENGINES",
    "DATA_SOURCE_STATUSES",
    "DEFINITION_CHANGES",
    "DEFINITION_KINDS",
    "DEFINITION_STATUSES",
    "DOCUMENT_STATUSES",
    "EMBEDDING_DIMENSIONS",
    "EVENT_TYPES",
    "EXECUTION_STATUSES",
    "LLM_ROLES",
    "LLM_TIERS",
    "MESSAGE_ROLES",
    "PROFILE_STATUSES",
    "RELATIONSHIP_KINDS",
    "RUN_STATUSES",
    "SEMANTIC_ROLES",
    "SENSITIVITY_LEVELS",
    "SNAPSHOT_STATUSES",
    "TABLE_KINDS",
    "TENANT_TABLES",
    "TERMINAL_RUN_STATUSES",
    "USAGE_STATUSES",
    "AgentEvent",
    "AgentRun",
    "AuditLog",
    "Base",
    "CatalogColumn",
    "CatalogRelationship",
    "CatalogSnapshot",
    "CatalogTable",
    "ColumnPolicy",
    "Conversation",
    "DataSource",
    "Finding",
    "Invitation",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "Message",
    "OrgMembership",
    "OrgRecoveryGrant",
    "Organization",
    "QueryExecution",
    "ResultArtifact",
    "SecurityEvent",
    "SemanticDefinition",
    "SemanticDefinitionVersion",
    "UsageLedger",
    "User",
]

ROLE_CHECK = "role IN ({})".format(", ".join(f"'{role}'" for role in ROLES))

#: The engines a connector exists for.
DATA_SOURCE_ENGINES: tuple[str, ...] = ("pg", "mssql")

#: ``registered`` is what WP3.1 can honestly claim.
DATA_SOURCE_STATUSES: tuple[str, ...] = ("registered", "verified", "error")

#: A snapshot is built, then becomes the one active catalog for its data source.
SNAPSHOT_STATUSES: tuple[str, ...] = ("building", "active", "failed", "superseded")

TABLE_KINDS: tuple[str, ...] = ("table", "view")

#: ``declared`` is a foreign key the engine enforces.
RELATIONSHIP_KINDS: tuple[str, ...] = ("declared", "inferred")

#: What a column is *for*, which the DAL and the composer both reason about.
SEMANTIC_ROLES: tuple[str, ...] = ("measure", "dimension", "time", "id", "other")

#: ``suspected`` is the classifier's opinion and is enough to mask by default.
SENSITIVITY_LEVELS: tuple[str, ...] = ("none", "suspected", "confirmed")

#: What may be done with a column's values.
COLUMN_POLICIES: tuple[str, ...] = ("allow", "mask", "deny")

#: How far profiling got. ``partial`` is a normal outcome, not an error.
PROFILE_STATUSES: tuple[str, ...] = ("none", "partial", "complete")

#: The text search configuration table cards are indexed under.
CARD_TEXT_CONFIGURATION = "english"

#: The same configuration for knowledge chunks, and the same reasoning: a chunk is prose.
CHUNK_TEXT_CONFIGURATION = "english"

#: How wide `knowledge_chunks.embedding` is.
EMBEDDING_DIMENSIONS = 1536

#: A document is `pending` until it has been extracted, chunked and embedded.
DOCUMENT_STATUSES: tuple[str, ...] = ("pending", "indexed", "failed")

#: Architecture 5.4's two kinds (revision 0020).
DEFINITION_KINDS: tuple[str, ...] = ("metric", "dimension")

#: An imported definition constrains generated SQL.
DEFINITION_STATUSES: tuple[str, ...] = ("proposed", "active", "retired")

#: What put a definition into the state a version row records (revision 0022, B-088).
DEFINITION_CHANGES: tuple[str, ...] = (
    "created",
    "accepted",
    "updated",
    "retired",
    "reinstated",
)


class Organization(Base):
    """A tenant. Its ``id`` is the ``org_id`` every other tenant row carries."""

    __tablename__ = "organizations"

    id: Mapped[UuidPk]
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    settings: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: The database this organization asks questions of, chosen once by an Admin.
    active_data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "data_sources.id",
            ondelete="SET NULL",
            name="fk_organizations_active_data_source_id",
            use_alter=True,
        )
    )
    created_at: Mapped[CreatedAt]


class User(Base):
    """A person, identified by the IdP's subject claim."""

    __tablename__ = "users"

    id: Mapped[UuidPk]
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320))
    name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[CreatedAt]


class OrgMembership(Base):
    """Which role a user holds in an organization."""

    __tablename__ = "org_memberships"
    __table_args__ = (
        CheckConstraint(ROLE_CHECK, name="role_valid"),
        Index("ix_org_memberships_user_id", "user_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]


class Invitation(Base):
    """A pending invitation to join an organization."""

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(ROLE_CHECK, name="role_valid"),
        Index("ix_invitations_org_id_email", "org_id", "email"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    accepted_at: Mapped[datetime | None]
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]


class OrgRecoveryGrant(Base):
    """A way back into an organization whose Admins can no longer sign in (B-017)."""

    __tablename__ = "org_recovery_grants"
    __table_args__ = (Index("ix_org_recovery_grants_org_id", "org_id"),)

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: What this grant is for, in the Admin's own words.
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None]
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    revoked_at: Mapped[datetime | None]


class DataSource(Base):
    """A customer database this organization has registered (arch Part 5.1, 10.1)."""

    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint(
            "engine IN ({})".format(", ".join(f"'{engine}'" for engine in DATA_SOURCE_ENGINES)),
            name="engine_valid",
        ),
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{status}'" for status in DATA_SOURCE_STATUSES)),
            name="status_valid",
        ),
        # Two sources with one name in an organization is a support call waiting to happen.
        Index("uq_data_sources_org_id_name", "org_id", "name", unique=True),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    engine: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Safe to show and safe to log: "host:port/database", never a credential.
    host_display: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'registered'")
    )
    settings: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    secret_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Proven, never assumed (revision 0006).
    readonly_verified: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    last_verified_at: Mapped[datetime | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]


class CatalogSnapshot(Base):
    """One crawl of one customer database (architecture Part 5.2, 10.1)."""

    __tablename__ = "catalog_snapshots"
    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in SNAPSHOT_STATUSES)),
            name="status_valid",
        ),
        CheckConstraint(
            "profile_status IN ({})".format(", ".join(f"'{s}'" for s in PROFILE_STATUSES)),
            name="profile_status_valid",
        ),
        Index(
            "uq_catalog_snapshots_data_source_id_version",
            "data_source_id",
            "version",
            unique=True,
        ),
        # "Which catalog is current" must have exactly one answer.
        Index(
            "uq_catalog_snapshots_one_active",
            "data_source_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'building'")
    )
    captured_at: Mapped[CreatedAt]
    completed_at: Mapped[datetime | None]
    object_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    #: none until the profiler has run over this snapshot; ``partial`` when its budget stopped it.
    profile_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'none'")
    )
    profiled_at: Mapped[datetime | None]


class CatalogTable(Base):
    """A table or view as one snapshot found it."""

    __tablename__ = "catalog_tables"
    __table_args__ = (
        CheckConstraint(
            "kind IN ({})".format(", ".join(f"'{k}'" for k in TABLE_KINDS)), name="kind_valid"
        ),
        Index(
            "uq_catalog_tables_snapshot_id_schema_name_table_name",
            "snapshot_id",
            "schema_name",
            "table_name",
            unique=True,
        ),
        Index("ix_catalog_tables_card_tsv", "card_tsv", postgresql_using="gin"),
        # The backfill's work list (revision 0018, B-018): a card with text and no vector.
        Index(
            "ix_catalog_tables_unembedded",
            "org_id",
            "snapshot_id",
            postgresql_where=text("embedding IS NULL AND card_text IS NOT NULL"),
        ),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: sha256 over this table's shape.
    structural_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: The engine's own estimate, not a count (WP4.2 writes it).
    row_estimate: Mapped[int | None] = mapped_column(BigInteger)
    #: The prose an agent is given instead of a schema dump (WP4.3).
    card_text: Mapped[str | None] = mapped_column(Text)
    #: Where "this card still needs an embedding" is recorded.
    flags: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: Generated by the database, so the index can never disagree with the text it indexes.
    card_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            f"to_tsvector('{CARD_TEXT_CONFIGURATION}', COALESCE(card_text, ''))", persisted=True
        ),
    )
    #: The card's text as a vector (revision 0018, B-018).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


class CatalogColumn(Base):
    """A column of a catalogued table, and what a sample of it looked like."""

    __tablename__ = "catalog_columns"
    __table_args__ = (
        CheckConstraint(
            "semantic_role IS NULL OR semantic_role IN ({})".format(
                ", ".join(f"'{role}'" for role in SEMANTIC_ROLES)
            ),
            name="semantic_role_valid",
        ),
        CheckConstraint(
            "sensitivity IN ({})".format(", ".join(f"'{level}'" for level in SENSITIVITY_LEVELS)),
            name="sensitivity_valid",
        ),
        Index("uq_catalog_columns_table_id_name", "table_id", "name", unique=True),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_tables.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False)
    data_type: Mapped[str] = mapped_column(String(255), nullable=False)
    nullable: Mapped[bool] = mapped_column(nullable=False)
    is_pk: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text)

    null_frac: Mapped[float | None]
    distinct_est: Mapped[int | None] = mapped_column(BigInteger)
    min_val: Mapped[str | None] = mapped_column(Text)
    max_val: Mapped[str | None] = mapped_column(Text)
    top_values: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    semantic_role: Mapped[str | None] = mapped_column(String(20))
    sensitivity: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'none'")
    )
    #: How many rows the profile was computed from.
    sample_rows: Mapped[int | None]


class ColumnPolicy(Base):
    """What an Admin decided may be done with one column's values."""

    __tablename__ = "column_policies"
    __table_args__ = (
        CheckConstraint(
            "policy IN ({})".format(", ".join(f"'{policy}'" for policy in COLUMN_POLICIES)),
            name="policy_valid",
        ),
        Index(
            "uq_column_policies_column",
            "data_source_id",
            "schema_name",
            "table_name",
            "column_name",
            unique=True,
        ),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    policy: Mapped[str] = mapped_column(String(20), nullable=False)
    mask_type: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[CreatedAt]


class CatalogRelationship(Base):
    """A join the engine declares (architecture Part 5.2)."""

    __tablename__ = "catalog_relationships"
    __table_args__ = (
        CheckConstraint(
            "kind IN ({})".format(", ".join(f"'{k}'" for k in RELATIONSHIP_KINDS)),
            name="kind_valid",
        ),
        Index(
            "ix_catalog_relationships_snapshot_id_from_table",
            "snapshot_id",
            "from_schema",
            "from_table",
        ),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    constraint_name: Mapped[str] = mapped_column(String(255), nullable=False)
    from_schema: Mapped[str] = mapped_column(String(255), nullable=False)
    from_table: Mapped[str] = mapped_column(String(255), nullable=False)
    from_columns: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    to_schema: Mapped[str] = mapped_column(String(255), nullable=False)
    to_table: Mapped[str] = mapped_column(String(255), nullable=False)
    to_columns: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'declared'"))
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(precision=3, scale=2), nullable=False, server_default=text("1.0")
    )
    #: What was measured, for an ``inferred`` edge (revision 0032, D-050).
    evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)


class AuditLog(Base):
    """Append-only record of who did what (architecture Part 8.2)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_org_id_ts", "org_id", text("ts DESC")),)

    # bigserial per architecture Part 10.1.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(100))
    object_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    sensitive: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    ts: Mapped[CreatedAt]


#: What one execution ended as.
EXECUTION_STATUSES: tuple[str, ...] = ("ok", "error", "refused")


class QueryExecution(Base):
    """Every attempt to read a customer's database (architecture Part 8.2, 10.1)."""

    __tablename__ = "query_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in EXECUTION_STATUSES)),
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'refused') = (violation_code IS NOT NULL)",
            name="violation_code_matches_status",
        ),
        Index("ix_query_executions_org_id_created_at", "org_id", text("created_at DESC")),
        Index("ix_query_executions_org_id_sql_hash", "org_id", "sql_hash"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    #: SET NULL on delete: the record of what was read outlives the registration of the thing it...
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    #: SET NULL for the same reason ``data_source_id`` is (D-016).
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    sql_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Fully qualified names, from the AST rather than from the text.
    tables: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    columns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Set exactly when status is ``refused``, and enforced by a constraint.
    violation_code: Mapped[str | None] = mapped_column(String(40))
    row_count: Mapped[int | None]
    duration_ms: Mapped[int | None]
    #: Sanitized before it arrives here, by the connector or by the validator.
    error: Mapped[str | None] = mapped_column(Text)
    sensitive_accessed: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[CreatedAt]


class ResultArtifact(Base):
    """What a query returned, kept for as long as the customer allows."""

    __tablename__ = "result_artifacts"
    __table_args__ = (
        Index("ix_result_artifacts_execution", "query_execution_id"),
        Index("ix_result_artifacts_expires_at", "expires_at"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    query_execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("query_executions.id", ondelete="CASCADE"), nullable=False
    )
    #: Shape, not content: column names, row count, which columns were masked.
    summary: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    sample_rows: Mapped[list[list[object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    truncated: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    #: Where the full result lives in the configured store.
    storage_ref: Mapped[str | None] = mapped_column(String(500))
    #: Retention is a promise, so it is a column rather than a habit.
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[CreatedAt]


#: Architecture 4.9's roles and tiers, as the ledger stores them.
LLM_ROLES: tuple[str, ...] = ("intake", "observe", "plan", "sql", "critic", "compose", "embed")
#: `embed` is its own tier rather than `small` (revision 0017).
LLM_TIERS: tuple[str, ...] = ("small", "mid", "strong", "embed")

#: A provider call either answered or it did not.
USAGE_STATUSES: tuple[str, ...] = ("ok", "error")


class UsageLedger(Base):
    """One row per call to a model (architecture Part 4.9, 8.3)."""

    __tablename__ = "usage_ledger"
    __table_args__ = (
        CheckConstraint(
            "role IN ({})".format(", ".join(f"'{role}'" for role in LLM_ROLES)), name="role_valid"
        ),
        CheckConstraint(
            "tier IN ({})".format(", ".join(f"'{tier}'" for tier in LLM_TIERS)), name="tier_valid"
        ),
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in USAGE_STATUSES)),
            name="status_valid",
        ),
        CheckConstraint("(status = 'error') = (error IS NOT NULL)", name="error_matches_status"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0", name="token_counts_non_negative"
        ),
        # Cached input is a subset of the input, never an addition (revision 0034).
        CheckConstraint(
            "cached_input_tokens IS NULL OR "
            "(cached_input_tokens >= 0 AND cached_input_tokens <= input_tokens)",
            name="cached_within_input",
        ),
        Index("ix_usage_ledger_org_id_created_at", "org_id", text("created_at DESC")),
        Index("ix_usage_ledger_org_id_run_id", "org_id", "run_id"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    #: SET NULL rather than CASCADE: what a question cost is still true after the run row is gone.
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    tier: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    #: How many of ``input_tokens`` the provider served from its prompt cache.
    cached_input_tokens: Mapped[int | None] = mapped_column()
    #: True when the counts are our own arithmetic rather than the provider's.
    tokens_estimated: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    #: Null means not priced, never free.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(precision=12, scale=6))
    latency_ms: Mapped[int | None]
    #: The second call of a parse-then-repair pair.
    repaired: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    #: Sanitized before it arrives: providers raise nothing that has not been.
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]


#: Architecture 10.1's run status domain.
RUN_STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "validating",
    "completed",
    "interrupted",
    "failed",
    "budget_exhausted",
)

#: The endings. A run in one of these is finished and cannot move again.
TERMINAL_RUN_STATUSES: tuple[str, ...] = (
    "completed",
    "interrupted",
    "failed",
    "budget_exhausted",
)

MESSAGE_ROLES: tuple[str, ...] = ("user", "assistant")

#: Architecture 10.3's event vocabulary, closed on purpose.
EVENT_TYPES: tuple[str, ...] = (
    "run_started",
    "intent_classified",
    "context_selected",
    "capability_checked",
    "plan_created",
    "step_started",
    "tool_called",
    "knowledge_consulted",
    "model_called",
    "sql_validated",
    "sql_rejected",
    "query_executed",
    "result_summarized",
    "finding_added",
    "hypothesis_updated",
    "reflection",
    "critic_verdict",
    "budget_warning",
    "budget_exhausted",
    "answer_composed",
    "run_finished",
    "error",
)

#: How sure the agent is of a finding, in architecture 10.3's own words.
CONFIDENCE_LEVELS: tuple[str, ...] = ("high", "medium", "low")


class Conversation(Base):
    """A thread of questions, and the runs they started (architecture 10.1)."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_org_id_created_at", "org_id", text("created_at DESC")),
        Index("ix_conversations_data_source_id", "data_source_id"),
        Index("ix_conversations_user_archived", "user_id", "archived_at"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("data_sources.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(300))
    #: When this thread was put away, or NULL while it is still in the list (revision 0026, D-039).
    archived_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]


#: The three endings a finished run can have (D-044).
RUN_OUTCOME_STATES: tuple[str, ...] = ("answered", "partly", "refused")


class AgentRun(Base):
    """One question, from asked to answered (architecture Part 10.1, 4.4)."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in RUN_STATUSES)), name="status_valid"
        ),
        # "Finished but with no finish time" is the shape a crashed transition leaves behind.
        CheckConstraint(
            "(status IN ({})) = (finished_at IS NOT NULL)".format(
                ", ".join(f"'{s}'" for s in TERMINAL_RUN_STATUSES)
            ),
            name="finished_at_matches_status",
        ),
        # Declared here as well as in revision 0030.
        CheckConstraint(
            "outcome_state IS NULL OR outcome_state IN ({})".format(
                ", ".join(f"'{state}'" for state in RUN_OUTCOME_STATES)
            ),
            name="outcome_state_valid",
        ),
        # The property the card depends on, enforced where it cannot be edited away.
        CheckConstraint(
            "outcome_state <> 'partly' OR (unanswered IS NOT NULL AND unanswered <> '')",
            name="partly_names_what_is_missing",
        ),
        Index(
            "ix_agent_runs_org_id_conversation_id_created_at",
            "org_id",
            "conversation_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    #: The Meta model the person picked for this question; null means the configured default.
    model: Mapped[str | None] = mapped_column(Text)
    budget: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    state: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: A rollup for the trace UI; ``usage_ledger`` stays authoritative.
    model_usage: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: Null means unpriced, never free — the same rule ``cost_usd`` follows.
    cost_estimate: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=4))
    #: What this answer does not establish, in plain words: a budget that stopped the search.
    chart: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    limitations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: One line on how the answer was reached, for the reader who will not open the SQL.
    method: Mapped[str | None] = mapped_column(Text)
    #: How the run ended: `answered` | `partly` | `refused` (B-134, D-044, revision 0030).
    outcome_state: Mapped[str | None] = mapped_column(Text)
    #: The part of the question the run could not answer, in the composer's words.
    unanswered: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    #: Sanitized before it arrives, like every other error column here.
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]


class Message(Base):
    """What was said, by the person and by the agent (architecture 10.1)."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ({})".format(", ".join(f"'{r}'" for r in MESSAGE_ROLES)), name="role_valid"
        ),
        Index(
            "ix_messages_org_id_conversation_id_created_at",
            "org_id",
            "conversation_id",
            "created_at",
        ),
        # Partial, so the agent's own messages — which carry no key.
        Index(
            "uq_messages_idempotency_key",
            "org_id",
            "conversation_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[CreatedAt]


class AgentEvent(Base):
    """One step of one run, as the trace will show it (architecture 10.3)."""

    __tablename__ = "agent_events"
    __table_args__ = (
        CheckConstraint(
            "type IN ({})".format(", ".join(f"'{t}'" for t in EVENT_TYPES)), name="type_valid"
        ),
        CheckConstraint("seq > 0", name="seq_positive"),
        UniqueConstraint("run_id", "seq", name="uq_agent_events_run_id_seq"),
        Index("ix_agent_events_org_id_run_id_seq", "org_id", "run_id", "seq"),
    )

    # bigserial per architecture 10.1.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Built for eyes (arch 10.3): short public strings out of structured tool output.
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ts: Mapped[CreatedAt]


class Finding(Base):
    """Something the run concluded, and what backs it up (architecture 10.1)."""

    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "confidence IN ({})".format(", ".join(f"'{c}'" for c in CONFIDENCE_LEVELS)),
            name="confidence_valid",
        ),
        Index("ix_findings_org_id_run_id", "org_id", "run_id"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    support: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'medium'")
    )
    #: True when the composed answer rests on this finding.
    cited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[CreatedAt]


class KnowledgeDocument(Base):
    """Something an organization wrote down (architecture 5.5, 10.1)."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in DOCUMENT_STATUSES)),
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)",
            name="failure_reason_matches_status",
        ),
        Index("ix_knowledge_documents_org_id_created_at", "org_id", text("created_at DESC")),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    #: An `ArtifactStore` key, org-prefixed and checked, not a filesystem path.
    blob_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    #: ``SET NULL`` per D-016: removing a person must not delete the record of what their...
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]
    indexed_at: Mapped[datetime | None]


class KnowledgeChunk(Base):
    """One passage of a document, as retrieval will find it (architecture 5.5)."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "seq", name="uq_knowledge_chunks_document_id_seq"),
        Index("ix_knowledge_chunks_org_id_document_id", "org_id", "document_id"),
        Index("ix_knowledge_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_knowledge_chunks_unembedded",
            "org_id",
            "document_id",
            postgresql_where=text("embedding IS NULL"),
        ),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    #: ``CASCADE``, and deliberately not D-016's ``SET NULL``.
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(nullable=False)
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    #: The heading trail, outermost first: `["Revenue policy", "Exclusions"]`.
    headings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    token_estimate: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    #: Generated by the database. Never assigned in Python — writing ``text`` is what updates it.
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(f"to_tsvector('{CHUNK_TEXT_CONFIGURATION}', text)", persisted=True),
    )
    created_at: Mapped[CreatedAt]


#: Every tenant-scoped table mapped to the column that identifies its tenant.


#: `active` is shown to the planner; `retired` is kept and shown to nobody.
VERIFIED_STATUSES = ("active", "retired")


class SemanticDefinition(Base):
    """What a metric means here, in a form a check can read (arch 5.4, D-033)."""

    __tablename__ = "semantic_definitions"
    __table_args__ = (
        CheckConstraint(
            "kind IN ({})".format(", ".join(f"'{k}'" for k in DEFINITION_KINDS)), name="kind_valid"
        ),
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in DEFINITION_STATUSES)),
            name="status_valid",
        ),
        UniqueConstraint(
            "data_source_id", "name", name="uq_semantic_definitions_data_source_id_name"
        ),
        Index("ix_semantic_definitions_org_id_data_source_id", "org_id", "data_source_id"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    #: Lowercased by the service: "Net Revenue" and "net_revenue" are one metric.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'metric'"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    #: `sum(orders.total_amount)`. Rendered into the prompt, not parsed and not enforced.
    expression: Mapped[str | None] = mapped_column(Text)
    #: `[{"table": …, "column": …, "op": …, "values": [...]}]`, the half the critic can act on.
    required_filters: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: The words a person might use.
    synonyms: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: What this definition makes the answer say, or None (revision 0033).
    caveat: Mapped[str | None] = mapped_column(Text)
    #: Where it came from, when it was not typed (B-059, WP10.2d).
    provenance: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    #: Which row of ``semantic_definition_versions`` this one currently is (revision 0022, B-088).
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]
    #: Bumped by the service on every edit.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class SemanticDefinitionVersion(Base):
    """Every state a definition has been in force in (revision 0022, B-088)."""

    __tablename__ = "semantic_definition_versions"
    __table_args__ = (
        CheckConstraint(
            "change IN ({})".format(", ".join(f"'{c}'" for c in DEFINITION_CHANGES)),
            name="change_valid",
        ),
        UniqueConstraint(
            "definition_id",
            "version",
            name="uq_semantic_definition_versions_definition_id_version",
        ),
        Index("ix_semantic_definition_versions_org_id_definition_id", "org_id", "definition_id"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    definition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("semantic_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expression: Mapped[str | None] = mapped_column(Text)
    required_filters: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    synonyms: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: Mirrored from the live row (revision 0033).
    caveat: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    #: What put it into this state: created, accepted, updated or retired.
    change: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]


class VerifiedQuery(Base):
    """An Admin-approved question and the SQL that answers it (arch 5.4)."""

    __tablename__ = "verified_queries"
    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in VERIFIED_STATUSES)),
            name="status_valid",
        ),
        UniqueConstraint(
            "data_source_id", "question", name="uq_verified_queries_data_source_id_question"
        ),
        Index("ix_verified_queries_org_id_data_source_id", "org_id", "data_source_id"),
    )

    id: Mapped[UuidPk]
    org_id: Mapped[OrgId] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    #: In the words a person would ask it.
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql: Mapped[str] = mapped_column(Text, nullable=False)
    #: Why this shape is the right one.
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


TENANT_TABLES: dict[str, str] = {
    "organizations": "id",
    "org_memberships": "org_id",
    "invitations": "org_id",
    "audit_log": "org_id",
    "data_sources": "org_id",
    "column_policies": "org_id",
    "catalog_snapshots": "org_id",
    "catalog_tables": "org_id",
    "catalog_columns": "org_id",
    "catalog_relationships": "org_id",
    "query_executions": "org_id",
    "result_artifacts": "org_id",
    "usage_ledger": "org_id",
    "conversations": "org_id",
    "agent_runs": "org_id",
    "messages": "org_id",
    "agent_events": "org_id",
    "findings": "org_id",
    "knowledge_documents": "org_id",
    "knowledge_chunks": "org_id",
    "semantic_definitions": "org_id",
    "semantic_definition_versions": "org_id",
    "verified_queries": "org_id",
    "org_recovery_grants": "org_id",
}
