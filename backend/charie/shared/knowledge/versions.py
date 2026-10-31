"""Draft versions: every learning run builds one (P07.3 copies the published one)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.learner.locks import RunActiveError, serialize_learning_runs
from charie.shared.db import get_session
from charie.shared.errors import ApiError
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


VOLATILE_DETAILS = frozenset({"tests", "reported_checks", "sql_preview", "tested_at", "sources"})


class VersionNotFound(LookupError):
    """No version with that id."""


class PublishError(ValueError):
    """Only a draft can become published."""


class PublishBlocked(ValueError):
    """Big changes wait for the owner's review."""


def _stable(entry: dict | None) -> dict:
    """What a change compares: meaning and non-volatile details."""
    entry = entry if isinstance(entry, dict) else {}
    details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    return {
        "title": entry.get("title"),
        "meaning": entry.get("meaning"),
        "details": {key: value for key, value in details.items() if key not in VOLATILE_DETAILS},
    }


def is_big_change(kind: str, change: str, before: dict | None, after: dict | None) -> bool:
    """Whether one `kb_changes` row must wait for the owner's review.

    Removals, conflicts, failed checks, new or changed recipes, rules,
    links and dimensions are big; owner confirmations, fresh evidence and
    clear new values are small.
    """
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    if change == "removed":
        return True
    if after.get("confidence") == "conflicting":
        return True
    if after.get("confidence") == "confirmed" and before.get("confidence") != "confirmed":
        return False
    tests = after.get("tests") or []
    if any(isinstance(check, dict) and check.get("passed") is False for check in tests):
        return True
    if kind == "metric":
        if change == "added":
            return True
        return _stable(before) != _stable(after)
    if kind == "rule":
        return True
    return kind in ("link", "dimension") and change == "changed"


def _row_is_big(row) -> bool:
    """The stored flag, or a live classification of the row's contents."""
    if row.is_big:
        return True
    before = row.before if isinstance(row.before, dict) else {}
    after = row.after if isinstance(row.after, dict) else {}
    kind = after.get("kind") or before.get("kind") or ""
    return is_big_change(kind, row.change, before, after)


def big_changes(session: Session, version_id: int) -> list:
    """Every change of a version that must wait for review."""
    from charie.shared.tables.knowledge import KbChange

    rows = session.scalars(
        select(KbChange).where(KbChange.version_id == version_id).order_by(KbChange.id)
    ).all()
    return [row for row in rows if _row_is_big(row)]


def publish_version(session: Session, version_id: int):
    """Publish one draft: the live version becomes archived, atomically.

    Publishing an already-published version is idempotent. Anything else
    that isn't a draft is refused, as are drafts with big changes. Version
    ids never change, so active chats stay pinned. The caller commits.
    """
    from charie.shared.tables.knowledge import KbVersion

    serialize_learning_runs(session)
    version = session.get(KbVersion, version_id, with_for_update=True)
    if version is None:
        raise VersionNotFound(f"There's no knowledge version {version_id}.")
    if version.status == "published":
        return version
    if version.status != "draft":
        raise PublishError("Only a draft can be published.")
    big = big_changes(session, version_id)
    if big:
        raise PublishBlocked(
            f"Version {version.number} has {len(big)} big change(s). Review them first."
        )
    live = session.scalar(
        select(KbVersion)
        .where(KbVersion.status == "published", KbVersion.id != version.id)
        .with_for_update()
    )
    if live is not None:
        live.status = "archived"
    version.status = "published"
    from datetime import UTC, datetime

    version.published_at = datetime.now(UTC)
    session.flush()
    return version


def finalize_run(session: Session, version_id: int) -> dict:
    """The shared auto-publish policy for later refresh and owner-answer runs.

    Publishes only after setup, for a non-owner draft whose every change
    is small and whose checks all pass. Anything else stays for review.
    The caller commits.
    """
    from charie.shared.settings import get_setting
    from charie.shared.tables.knowledge import KbVersion

    version = session.get(KbVersion, version_id)
    if version is None:
        return {"published": False, "version": None, "reason": "That version is gone."}
    if version.status != "draft":
        return {
            "published": False,
            "version": version.number,
            "reason": "Only a draft can be published.",
        }
    if not get_setting(session, "setup_done"):
        return {
            "published": False,
            "version": version.number,
            "reason": "Setup isn't finished yet.",
        }
    if version.made_by == "owner_edit":
        return {
            "published": False,
            "version": version.number,
            "reason": "A waiting owner draft stays for review.",
        }
    big = big_changes(session, version_id)
    if big:
        return {
            "published": False,
            "version": version.number,
            "reason": f"{len(big)} big change(s) stay for review.",
        }
    failed = _failed_metrics(session, version_id)
    if failed:
        return {
            "published": False,
            "version": version.number,
            "reason": f"{len(failed)} number(s) fail their checks.",
        }
    conflicts = _conflicting_entries(session, version_id)
    if conflicts:
        return {
            "published": False,
            "version": version.number,
            "reason": f"{len(conflicts)} conflict(s) stay for review.",
        }
    published = publish_version(session, version_id)
    return {"published": True, "version": published.number, "reason": "Every change is small."}


def _failed_metrics(session: Session, version_id: int) -> list[str]:
    """Metric keys with a failed check in the version."""
    from charie.shared.knowledge.store import list_entries

    failed = []
    for entry in list_entries(session, version_id, kinds=["metric"]):
        tests = entry.details.get("tests") if isinstance(entry.details, dict) else []
        if any(isinstance(check, dict) and check.get("passed") is False for check in tests or []):
            failed.append(entry.key)
    return sorted(failed)


def _conflicting_entries(session: Session, version_id: int) -> list[str]:
    """Entry keys still marked conflicting in the version."""
    from charie.shared.knowledge.store import list_entries

    return sorted(
        entry.key
        for entry in list_entries(session, version_id)
        if entry.confidence == "conflicting"
    )


versions_router = APIRouter()


def _full_shape(version) -> dict:
    """The version object the screens use for review and publishing."""
    summary = version.summary if isinstance(version.summary, dict) else {}
    return {
        "id": version.id,
        "number": version.number,
        "status": version.status,
        "made_by": version.made_by,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "summary": {
            "added": summary.get("added", 0),
            "changed": summary.get("changed", 0),
            "removed": summary.get("removed", 0),
            "note": summary.get("note", ""),
        },
    }


def _change_shape(row) -> dict:
    """One reviewed change: actual before/after entries, never a guess."""
    before = row.before if isinstance(row.before, dict) else None
    after = row.after if isinstance(row.after, dict) else None
    title = (after or {}).get("title") or (before or {}).get("title") or ""
    return {
        "key": row.key,
        "title": title,
        "change": row.change,
        "before": before,
        "after": after,
        "reason": row.reason or "",
        "is_big": bool(row.is_big),
    }


@versions_router.get("/api/versions")
def get_versions(session: Session = Depends(get_session)) -> dict:
    """Every version, newest first, with the live and draft numbers."""
    from charie.shared.tables.knowledge import KbVersion

    rows = session.scalars(select(KbVersion).order_by(KbVersion.number.desc())).all()
    live = next((row.number for row in rows if row.status == "published"), None)
    draft = next((row.number for row in rows if row.status == "draft"), None)
    return {"versions": [_full_shape(row) for row in rows], "live": live, "draft": draft}


@versions_router.get("/api/versions/{version_id}/changes")
def get_version_changes(version_id: int, session: Session = Depends(get_session)) -> dict:
    """What changed in one version, for Review changes."""
    from charie.shared.tables.knowledge import KbChange, KbVersion

    version = session.get(KbVersion, version_id)
    if version is None:
        raise ApiError(404, "not_found", "Charie couldn't find that version.")
    rows = session.scalars(
        select(KbChange).where(KbChange.version_id == version.id).order_by(KbChange.id)
    ).all()
    return {
        "version": version.number,
        "status": version.status,
        "changes": [_change_shape(row) for row in rows],
    }


@versions_router.post("/api/versions/{number}/publish")
def publish_version_number(number: int, session: Session = Depends(get_session)) -> dict:
    """Publish one draft; big changes and non-drafts are refused."""
    from charie.shared.tables.knowledge import KbVersion

    version = session.scalar(select(KbVersion).where(KbVersion.number == number))
    if version is None:
        raise ApiError(404, "not_found", "Charie couldn't find that version.")
    try:
        published = publish_version(session, version.id)
    except PublishBlocked as err:
        raise ApiError(409, "big_changes", str(err)) from err
    except PublishError as err:
        raise ApiError(409, "not_draft", str(err)) from err
    except RunActiveError as err:
        raise ApiError(409, "busy", str(err)) from err
    session.commit()
    session.refresh(published)
    return {"version": _full_shape(published)}
