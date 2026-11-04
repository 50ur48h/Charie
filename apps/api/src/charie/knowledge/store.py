"""Where an uploaded document's original bytes go (architecture 5.5, 9.1)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Protocol

__all__ = ["DocumentStore", "LocalDocumentStore", "StoredDocumentError", "extension_for"]

#: What each accepted format is saved as.
_EXTENSIONS = {
    "text/markdown": ".md",
    "text/plain": ".txt",
    "application/pdf": ".pdf",
}


class StoredDocumentError(Exception):
    """A document could not be written or read back."""


def extension_for(mime: str) -> str:
    return _EXTENSIONS.get(mime, ".bin")


class DocumentStore(Protocol):
    """One uploaded original, put somewhere it can be read back."""

    async def put(
        self, *, org_id: uuid.UUID, document_id: uuid.UUID, payload: bytes, mime: str
    ) -> str:
        """Write, and return the reference that finds it again."""
        ...

    async def get(self, *, org_id: uuid.UUID, reference: str) -> bytes | None:
        """Read it back, or None if it is gone."""
        ...


class LocalDocumentStore:
    """Files under a directory. The development and single-node answer."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def put(
        self, *, org_id: uuid.UUID, document_id: uuid.UUID, payload: bytes, mime: str
    ) -> str:
        reference = f"{org_id}/docs/{document_id}{extension_for(mime)}"
        destination = self._resolve(org_id, reference)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return reference

    async def get(self, *, org_id: uuid.UUID, reference: str) -> bytes | None:
        path = self._resolve(org_id, reference)
        return path.read_bytes() if path.is_file() else None

    def _resolve(self, org_id: uuid.UUID, reference: str) -> Path:
        prefix = f"{org_id}/"
        if not reference.startswith(prefix):
            raise StoredDocumentError("That document belongs to another organization.")
        # Resolved and re-checked, so a reference carrying `..` cannot climb out of the root...
        candidate = (self._root / reference).resolve()
        root = self._root.resolve()
        if not candidate.is_relative_to(root):
            raise StoredDocumentError("That document reference is not inside the store.")
        return candidate
