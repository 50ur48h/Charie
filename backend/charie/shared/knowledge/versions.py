"""Draft versions: every learning run builds one (P07.1 creates the row only)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.tables.knowledge import KbVersion


def get_draft(session: Session) -> KbVersion | None:
    """The open draft, if any."""
    return session.scalar(select(KbVersion).where(KbVersion.status == "draft").limit(1))


def get_published(session: Session) -> KbVersion | None:
    """The published version, if any."""
    return session.scalar(select(KbVersion).where(KbVersion.status == "published").limit(1))


def get_or_create_draft(session: Session, made_by: str) -> KbVersion:
    """The open draft, or a new empty one numbered after the last version."""
    draft = get_draft(session)
    if draft is not None:
        return draft
    last = session.scalar(select(func.max(KbVersion.number)))
    draft = KbVersion(number=(last or 0) + 1, status="draft", made_by=made_by)
    session.add(draft)
    session.flush()
    return draft
