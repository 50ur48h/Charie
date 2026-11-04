"""row-level security, the application role, and append-only audit_log"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"
POLICY = "org_isolation"

#: table -> the column that identifies its tenant.
TENANT_TABLES: dict[str, str] = {
    "organizations": "id",
    "org_memberships": "org_id",
    "invitations": "org_id",
    "audit_log": "org_id",
}


def upgrade() -> None:
    # Idempotent: the role is a cluster-level object.
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            END IF;
        END
        $$;
    """)

    op.execute(f"""
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO {APP_ROLE}', current_database());
        END
        $$;
    """)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    # Identity columns draw from a sequence; without USAGE, every audit insert fails.
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")

    # Tables added by later revisions inherit the same grants.
    op.execute(f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}
    """)
    op.execute(f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}
    """)

    # Append-only, enforced by the database rather than by discipline (architecture Part 8.2).
    op.execute(f"REVOKE UPDATE, DELETE ON audit_log FROM {APP_ROLE}")

    for table, key in TENANT_TABLES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # USING filters what can be read.
        op.execute(f"""
            CREATE POLICY {POLICY} ON {table}
            USING ({key} = current_setting('app.org_id')::uuid)
            WITH CHECK ({key} = current_setting('app.org_id')::uuid)
        """)


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}
    """)
    op.execute(f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
        REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}
    """)
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"""
        DO $$
        BEGIN
            EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM {APP_ROLE}', current_database());
        END
        $$;
    """)

    # The role itself is deliberately left in place: it is cluster-wide.
