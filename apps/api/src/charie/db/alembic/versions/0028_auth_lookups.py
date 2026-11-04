"""Five SECURITY DEFINER lookups, so the API can stop being the owner (B-123)"""

from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

APP_ROLE = "charie_app"

#: The statuses a run can be left in by a restart.
ORPHANABLE = ("queued", "running", "validating")

_FUNCTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "auth_membership_role",
        "p_user_id uuid, p_org_id uuid",
        """
        RETURNS text
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT m.role
            FROM org_memberships m
            WHERE m.user_id = p_user_id AND m.org_id = p_org_id
        $$
        """,
    ),
    (
        "auth_memberships_for_user",
        "p_user_id uuid",
        """
        RETURNS TABLE (org_id uuid, org_name varchar, member_role varchar)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT m.org_id, o.name, m.role
            FROM org_memberships m
            JOIN organizations o ON o.id = m.org_id
            WHERE m.user_id = p_user_id
            ORDER BY o.name
        $$
        """,
    ),
    (
        "auth_invitation_by_token",
        "p_token_hash varchar",
        """
        RETURNS TABLE (
            id uuid,
            org_id uuid,
            org_name varchar,
            member_role varchar,
            expires_at timestamptz,
            accepted_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT i.id, i.org_id, o.name, i.role, i.expires_at, i.accepted_at
            FROM invitations i
            JOIN organizations o ON o.id = i.org_id
            WHERE i.token_hash = p_token_hash
        $$
        """,
    ),
    (
        "auth_recovery_grant_by_token",
        "p_token_hash varchar",
        """
        RETURNS TABLE (
            id uuid,
            org_id uuid,
            org_name varchar,
            expires_at timestamptz,
            used_at timestamptz,
            revoked_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT g.id, g.org_id, o.name, g.expires_at, g.used_at, g.revoked_at
            FROM org_recovery_grants g
            JOIN organizations o ON o.id = g.org_id
            WHERE g.token_hash = p_token_hash
        $$
        """,
    ),
    (
        "ops_orphaned_runs",
        "",
        f"""
        RETURNS TABLE (run_id uuid, org_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT r.id, r.org_id
            FROM agent_runs r
            WHERE r.status IN ({", ".join(f"'{s}'" for s in ORPHANABLE)})
        $$
        """,
    ),
)


def upgrade() -> None:
    for name, args, body in _FUNCTIONS:
        op.execute(f"CREATE OR REPLACE FUNCTION {name}({args}) {body}")
        # Revoke first. A SECURITY DEFINER function is executable by PUBLIC the moment it exists.
        op.execute(f"REVOKE ALL ON FUNCTION {name}({args}) FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {name}({args}) TO {APP_ROLE}")


def downgrade() -> None:
    for name, args, _ in reversed(_FUNCTIONS):
        op.execute(f"DROP FUNCTION IF EXISTS {name}({args})")
