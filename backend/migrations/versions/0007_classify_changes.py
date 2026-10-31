"""Backfill big-change flags with the P09.9 severity rules (P09.9)."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_STRIP = "ARRAY['tests', 'reported_checks', 'sql_preview', 'tested_at', 'sources']"

_FAILED_TESTS = """EXISTS (
    SELECT 1
    FROM jsonb_array_elements(COALESCE(after->'tests', '[]'::jsonb)) AS t(item)
    WHERE (t.item->>'passed')::boolean IS FALSE
  )"""

_STABLE_METRIC = f"""(
    COALESCE(after->>'kind', '') = 'metric' AND NOT (
      change = 'changed'
      AND COALESCE(after->>'title', '') = COALESCE(before->>'title', '')
      AND COALESCE(after->>'meaning', '') = COALESCE(before->>'meaning', '')
      AND (COALESCE(after->'details', '{{}}') - {_STRIP})
        = (COALESCE(before->'details', '{{}}') - {_STRIP})
    )
  )"""

_BACKFILL = f"""
UPDATE kb_changes SET is_big = true
WHERE NOT is_big AND (
  change = 'removed'
  OR COALESCE(before->>'confidence', '') = 'conflicting'
  OR COALESCE(after->>'confidence', '') = 'conflicting'
  OR {_FAILED_TESTS}
  OR COALESCE(after->>'kind', '') = 'rule'
  OR {_STABLE_METRIC}
  OR COALESCE(after->>'kind', '') IN ('link', 'dimension') AND change = 'changed'
)
"""

_UNDO = f"""
UPDATE kb_changes SET is_big = false
WHERE is_big AND (
  change = 'removed'
  OR COALESCE(before->>'confidence', '') = 'conflicting'
  OR COALESCE(after->>'confidence', '') = 'conflicting'
  OR {_FAILED_TESTS}
  OR COALESCE(after->>'kind', '') = 'rule'
  OR {_STABLE_METRIC}
  OR COALESCE(after->>'kind', '') IN ('link', 'dimension') AND change = 'changed'
)
"""


def upgrade() -> None:
    op.execute(_BACKFILL)


def downgrade() -> None:
    op.execute(_UNDO)
