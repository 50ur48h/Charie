"""`GET /api/knowledge` and `GET /api/knowledge/{key}` in both apps (P07.4).

The list and one entry, from the published version or (in the Learner)
the draft. The chat app only ever shows the published version.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.knowledge.store import KIND_ORDER, entry_to_dict, get_entry, list_entries
from charie.shared.knowledge.versions import get_draft, get_published
from charie.shared.tables.knowledge import KbChange, KbVersion

KINDS = set(KIND_ORDER)

# The list shows the first 200 characters; the full meaning is in the detail.
MEANING_CUT = 200


def _version_shape(version: KbVersion, session: Session) -> dict:
    """The `version` object both screens use for the banner and counts."""
    changes = session.scalar(
        select(func.count()).select_from(KbChange).where(KbChange.version_id == version.id)
    )
    summary = version.summary if isinstance(version.summary, dict) else {}
    return {
        "id": version.id,
        "number": version.number,
        "status": version.status,
        "changes": changes or 0,
        "summary": {
            "added": summary.get("added", 0),
            "changed": summary.get("changed", 0),
            "removed": summary.get("removed", 0),
            "note": summary.get("note", ""),
        },
    }


def _entry_shape(entry, session: Session) -> dict:
    """One list row: the key, kind, title and the first 200 characters."""
    del session  # The row needs no extra queries.
    meaning = entry.meaning or ""
    return {
        "key": entry.key,
        "kind": entry.kind,
        "title": entry.title,
        "meaning": meaning[:MEANING_CUT],
        "confidence": entry.confidence,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def _parse_kinds(raw: str | None) -> list[str] | None:
    """One kind or several, comma-separated; unknown kinds are refused."""
    if raw is None:
        return None
    kinds = [piece.strip() for piece in raw.split(",") if piece.strip()]
    for kind in kinds:
        if kind not in KINDS:
            raise ApiError(400, "bad_kind", f"Unknown kind: {kind}.")
    return kinds or None


def _resolve_version(session: Session, raw: str, allow_draft: bool) -> KbVersion | None:
    """Published by default; the Learner may ask for the draft or a number."""
    if raw == "published":
        return get_published(session)
    if raw == "draft":
        if not allow_draft:
            raise ApiError(400, "bad_version", "The chat app only shows the published knowledge.")
        return get_draft(session) or get_published(session)
    try:
        number = int(raw)
    except ValueError:
        raise ApiError(
            400, "bad_version", f"Unknown version: {raw}. Ask for published or draft."
        ) from None
    version = session.scalar(select(KbVersion).where(KbVersion.number == number))
    if version is None:
        raise ApiError(404, "not_found", f"There's no knowledge version {number}.")
    if version.status != "published" and not allow_draft:
        raise ApiError(400, "bad_version", "The chat app only shows the published knowledge.")
    return version


def make_knowledge_router(allow_draft: bool) -> APIRouter:
    """The two reading addresses; the Learner mounts them with drafts allowed."""
    router = APIRouter()

    @router.get("/api/knowledge")
    def get_knowledge(
        kind: str | None = None,
        q: str | None = None,
        version: str = "published",
        session: Session = Depends(get_session),
    ) -> dict:
        resolved = _resolve_version(session, version, allow_draft)
        if resolved is None:
            return {"version": None, "entries": [], "counts": {}, "needs_review": 0}
        kinds = _parse_kinds(kind)
        entries = list_entries(session, resolved.id, kinds=kinds, q=q)
        counts = {name: 0 for name in KIND_ORDER}
        needs_review = 0
        for entry in list_entries(session, resolved.id):
            counts[entry.kind] = counts.get(entry.kind, 0) + 1
            if entry.confidence in ("guessed", "conflicting"):
                needs_review += 1
        return {
            "version": _version_shape(resolved, session),
            "entries": [_entry_shape(entry, session) for entry in entries],
            "counts": counts,
            "needs_review": needs_review,
        }

    @router.get("/api/knowledge/{key}")
    def get_knowledge_entry(
        key: str,
        version: str = "published",
        session: Session = Depends(get_session),
    ) -> dict:
        resolved = _resolve_version(session, version, allow_draft)
        if resolved is None:
            raise ApiError(404, "not_found", f"There's no knowledge entry called {key}.")
        entry = get_entry(session, resolved.id, key)
        if entry is None:
            raise ApiError(404, "not_found", f"There's no knowledge entry called {key}.")
        changes = session.scalars(
            select(KbChange).where(KbChange.key == key).order_by(KbChange.id.desc()).limit(10)
        ).all()
        numbers = dict(
            session.execute(
                select(KbVersion.id, KbVersion.number).where(
                    KbVersion.id.in_([change.version_id for change in changes])
                )
            ).all()
        )
        history = [
            {
                "version": numbers.get(change.version_id),
                "change": change.change,
                "reason": change.reason,
            }
            for change in changes
        ]
        return {
            "entry": entry_to_dict(entry),
            "version": _version_shape(resolved, session),
            "history": history,
        }

    return router
