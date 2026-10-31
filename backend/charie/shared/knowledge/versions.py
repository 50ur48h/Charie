"""Draft versions: every learning run builds one (P07.3 copies the published one)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.learner.locks import serialize_learning_runs
from charie.shared.tables.knowledge import KbEntry, KbVersion


def get_draft(session: Session) -> KbVersion | None:
    """The open draft, if any."""
    return session.scalar(select(KbVersion).where(KbVersion.status == "draft").limit(1))


def get_published(session: Session) -> KbVersion | None:
    """The published version, if any."""
    return session.scalar(select(KbVersion).where(KbVersion.status == "published").limit(1))


def get_or_create_draft(session: Session, made_by: str) -> KbVersion:
    """The open draft, or a new one numbered after the last version.

    A new draft copies every entry of the published version (if any),
    keeping keys. Copies write no `kb_changes`.
    """
    serialize_learning_runs(session)
    draft = get_draft(session)
    if draft is not None:
        return draft
    last = session.scalar(select(func.max(KbVersion.number)))
    draft = KbVersion(number=(last or 0) + 1, status="draft", made_by=made_by)
    session.add(draft)
    session.flush()
    published = get_published(session)
    if published is not None:
        entries = session.scalars(select(KbEntry).where(KbEntry.version_id == published.id)).all()
        for entry in entries:
            session.add(
                KbEntry(
                    version_id=draft.id,
                    key=entry.key,
                    kind=entry.kind,
                    title=entry.title,
                    meaning=entry.meaning,
                    details=dict(entry.details),
                    confidence=entry.confidence,
                    sources=list(entry.sources),
                    embedding=list(entry.embedding) if entry.embedding is not None else None,
                )
            )
        session.flush()
    return draft
