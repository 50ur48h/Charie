"""Frozen knowledge for the analyst's laptop tests (P10.4).

`export` reads the local database and writes
`backend/tests/data/local/analyst_snapshot.json.gz`: the published
version and its entries (no embeddings), the learned documents and
their sections (with embeddings), and the analyst settings.
`load_snapshot(session)` puts it in a test database. The file stays
out of git like the replays, and freezes the knowledge so the replays
stay valid. Re-export only when the published version changes, then
re-record the replays.
"""

import gzip
import json
import sys
from pathlib import Path

LOCAL_DIR = Path(__file__).resolve().parents[2] / "data" / "local"
SNAPSHOT_PATH = LOCAL_DIR / "analyst_snapshot.json.gz"

SETTING_KEYS = (
    "time_zone",
    "number_format",
    "show_reading",
    "answer_length",
    "thinking_minutes",
)


def _entry_shape(entry) -> dict:
    """One knowledge entry without its embedding."""
    return {
        "key": entry.key,
        "kind": entry.kind,
        "title": entry.title,
        "meaning": entry.meaning,
        "details": entry.details,
        "confidence": entry.confidence,
        "sources": entry.sources,
    }


def export_snapshot() -> Path:
    """Read the local database and write the snapshot file."""
    from sqlalchemy import select

    from charie.shared.db import session_scope
    from charie.shared.knowledge.store import list_entries
    from charie.shared.knowledge.versions import get_published
    from charie.shared.settings import get_setting
    from charie.shared.tables.sources import Document, DocumentSection

    with session_scope() as session:
        version = get_published(session)
        if version is None:
            raise SystemExit("No published version to snapshot.")
        payload = {
            "version": {
                "number": version.number,
                "status": version.status,
                "made_by": version.made_by,
            },
            "entries": [_entry_shape(entry) for entry in list_entries(session, version.id)],
            "documents": [
                {
                    "file_name": row.file_name,
                    "file_type": row.file_type,
                    "size_bytes": row.size_bytes,
                    "sha256": row.sha256,
                    "status": row.status,
                }
                for row in session.scalars(select(Document)).all()
            ],
            "sections": [],
            "settings": {key: get_setting(session, key) for key in SETTING_KEYS},
        }
        doc_ids = {row.sha256: row.id for row in session.scalars(select(Document)).all()}
        for row in session.scalars(select(DocumentSection)).all():
            payload["sections"].append(
                {
                    "document_sha256": next(
                        sha for sha, doc_id in doc_ids.items() if doc_id == row.document_id
                    ),
                    "position": row.position,
                    "heading_path": row.heading_path,
                    "text": row.text_,
                    "page_from": row.page_from,
                    "page_to": row.page_to,
                    "note": row.note,
                    "content_hash": row.content_hash,
                    "embedding": list(row.embedding) if row.embedding is not None else None,
                }
            )
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(SNAPSHOT_PATH, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return SNAPSHOT_PATH


def load_snapshot(session) -> int:
    """Put the snapshot in a test database; returns the version id."""
    from charie.shared.settings import set_setting
    from charie.shared.tables.knowledge import KbEntry, KbVersion
    from charie.shared.tables.sources import Document, DocumentSection

    with gzip.open(SNAPSHOT_PATH, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    saved = payload["version"]
    version = KbVersion(number=saved["number"], status=saved["status"], made_by=saved["made_by"])
    session.add(version)
    session.flush()
    for item in payload["entries"]:
        session.add(
            KbEntry(
                version_id=version.id,
                key=item["key"],
                kind=item["kind"],
                title=item["title"],
                meaning=item["meaning"],
                details=item["details"],
                confidence=item["confidence"],
                sources=item["sources"],
            )
        )
    doc_ids: dict[str, int] = {}
    for item in payload["documents"]:
        row = Document(
            file_name=item["file_name"],
            file_type=item["file_type"],
            size_bytes=item["size_bytes"],
            sha256=item["sha256"],
            status=item["status"],
        )
        session.add(row)
        session.flush()
        doc_ids[item["sha256"]] = row.id
    for item in payload["sections"]:
        session.add(
            DocumentSection(
                document_id=doc_ids[item["document_sha256"]],
                position=item["position"],
                heading_path=item["heading_path"],
                text_=item["text"],
                page_from=item["page_from"],
                page_to=item["page_to"],
                note=item["note"],
                content_hash=item["content_hash"],
                embedding=item["embedding"],
            )
        )
    for key, value in payload["settings"].items():
        set_setting(session, key, value)
    session.commit()
    return version.id


def main(argv: list[str]) -> int:
    """`export` writes the file; anything else names the one command."""
    if argv != ["export"]:
        print("usage: python -m tests.integration.chat.snapshot export")
        return 2
    print(export_snapshot())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
