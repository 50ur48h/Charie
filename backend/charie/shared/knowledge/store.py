"""Knowledge entries and the change log (P07.3).

The one place that writes `kb_entries` and `kb_changes` (with
`versions.py`). Entries only ever change inside a draft; published
versions are never edited.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.shared.knowledge.details import Source, check_details
from charie.shared.tables.knowledge import KbChange, KbEntry, KbVersion

# Architecture 05 section 3's kind table, in order, then title.
KIND_ORDER = (
    "table",
    "column",
    "link",
    "metric",
    "dimension",
    "rule",
    "style",
    "code",
    "event",
    "data_problem",
    "default",
    "calendar",
    "how_to",
    "example",
    "name",
    "data_range",
)


def _draft(session: Session, version_id: int) -> KbVersion:
    """The version, which must be an open draft."""
    version = session.get(KbVersion, version_id)
    if version is None:
        raise ValueError(f"No knowledge version {version_id}.")
    if version.status != "draft":
        raise ValueError("Knowledge only changes inside a draft.")
    return version


def entry_to_dict(entry: KbEntry) -> dict[str, Any]:
    """The entry as plain data, for `before`/`after` and the API."""
    return {
        "key": entry.key,
        "kind": entry.kind,
        "title": entry.title,
        "meaning": entry.meaning,
        "confidence": entry.confidence,
        "details": entry.details,
        "sources": entry.sources,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def get_entry(session: Session, version_id: int, key: str) -> KbEntry | None:
    """One entry of a version, if it has that key."""
    return session.scalar(
        select(KbEntry).where(KbEntry.version_id == version_id, KbEntry.key == key)
    )


def list_entries(
    session: Session,
    version_id: int,
    kinds: list[str] | None = None,
    q: str | None = None,
) -> list[KbEntry]:
    """Entries of a version: kind order from 05, then title.

    `q` matches when every word of it appears (any case) in the key,
    title or meaning.
    """
    entries = session.scalars(select(KbEntry).where(KbEntry.version_id == version_id)).all()
    words = q.split() if q else []
    found = []
    for entry in entries:
        if kinds is not None and entry.kind not in kinds:
            continue
        if words:
            haystack = f"{entry.key} {entry.title} {entry.meaning}".lower()
            if not all(word.lower() in haystack for word in words):
                continue
        found.append(entry)
    order = {kind: position for position, kind in enumerate(KIND_ORDER)}
    found.sort(key=lambda entry: (order.get(entry.kind, len(order)), entry.title))
    return found


def _write_change(
    session: Session,
    version_id: int,
    key: str,
    change: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    reason: str,
) -> None:
    """One `kb_changes` row; `is_big` waits for P09.9."""
    session.add(
        KbChange(
            version_id=version_id,
            key=key,
            change=change,
            before=before,
            after=after,
            reason=reason,
            is_big=False,
        )
    )


def upsert_entry(
    session: Session,
    version_id: int,
    key: str,
    kind: str,
    title: str,
    meaning: str,
    details: dict[str, Any] | None,
    confidence: str,
    sources: list[dict[str, Any]],
    reason: str,
) -> str:
    """Add or update one draft entry; returns added, changed or unchanged.

    Learning never overwrites what you confirmed: when the old entry is
    `confirmed` and the new one isn't, the old title, meaning and
    confidence stay, while details update and new sources are added.
    """
    _draft(session, version_id)
    checked = check_details(kind, details)
    checked_sources = [Source.model_validate(source).model_dump() for source in sources]
    old = get_entry(session, version_id, key)
    if old is None:
        entry = KbEntry(
            version_id=version_id,
            key=key,
            kind=kind,
            title=title,
            meaning=meaning,
            details=checked,
            confidence=confidence,
            sources=checked_sources,
            updated_at=datetime.now(UTC),
        )
        session.add(entry)
        session.flush()
        _write_change(session, version_id, key, "added", None, entry_to_dict(entry), reason)
        return "added"
    if old.confidence == "confirmed" and confidence != "confirmed":
        merged = list(old.sources)
        for source in checked_sources:
            if source not in merged:
                merged.append(source)
        new_values = {
            "kind": kind,
            "title": old.title,
            "meaning": old.meaning,
            "details": checked,
            "confidence": old.confidence,
            "sources": merged,
        }
    else:
        new_values = {
            "kind": kind,
            "title": title,
            "meaning": meaning,
            "details": checked,
            "confidence": confidence,
            "sources": checked_sources,
        }
    if all(getattr(old, field) == value for field, value in new_values.items()):
        return "unchanged"
    before = entry_to_dict(old)
    for field, value in new_values.items():
        setattr(old, field, value)
    old.updated_at = datetime.now(UTC)
    session.flush()
    _write_change(session, version_id, key, "changed", before, entry_to_dict(old), reason)
    return "changed"


def remove_entry(session: Session, version_id: int, key: str, reason: str) -> bool:
    """Delete one draft entry, and write `removed` with `before`."""
    _draft(session, version_id)
    entry = get_entry(session, version_id, key)
    if entry is None:
        return False
    _write_change(session, version_id, key, "removed", entry_to_dict(entry), None, reason)
    session.delete(entry)
    session.flush()
    return True


def _add_source(entry: KbEntry, source: dict[str, Any]) -> None:
    """One more source, unless it is already there."""
    checked = Source.model_validate(source).model_dump()
    if checked not in entry.sources:
        entry.sources = [*entry.sources, checked]


def edit_entry(
    session: Session,
    version_id: int,
    key: str,
    title: str | None = None,
    meaning: str | None = None,
    mark_wrong: bool = False,
) -> bool:
    """Your edit to a draft entry: it becomes `confirmed` with your source.

    `mark_wrong` instead marks it `guessed`. Owner edits never write
    `kb_changes`: the draft itself is the change under review.
    """
    _draft(session, version_id)
    entry = get_entry(session, version_id, key)
    if entry is None:
        return False
    if mark_wrong:
        entry.confidence = "guessed"
        _add_source(entry, {"type": "owner_edit", "text": "Marked as wrong by you"})
    else:
        if title is not None:
            entry.title = title
        if meaning is not None:
            entry.meaning = meaning
        entry.confidence = "confirmed"
        _add_source(entry, {"type": "owner_edit", "text": "Edited by you"})
    entry.updated_at = datetime.now(UTC)
    session.flush()
    return True


def approve_entry(session: Session, version_id: int, key: str) -> bool:
    """Your approval: the entry becomes `confirmed` with your source.

    Approving a `confirmed` entry changes nothing.
    """
    _draft(session, version_id)
    entry = get_entry(session, version_id, key)
    if entry is None or entry.confidence == "confirmed":
        return False
    entry.confidence = "confirmed"
    _add_source(entry, {"type": "owner_approval", "text": "Approved by you"})
    entry.updated_at = datetime.now(UTC)
    session.flush()
    return True
