"""Where a result is kept (architecture Part 7.6, 10.1)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol, cast, runtime_checkable

from charie.config import Settings, get_settings
from charie.dal.masking import MaskedFrame

__all__ = [
    "ArtifactStore",
    "BlobArtifactStore",
    "LocalArtifactStore",
    "StoredArtifactError",
    "artifact_store",
    "encode",
    "expires_at",
    "summarize",
]


class StoredArtifactError(Exception):
    """The result could not be stored."""


@runtime_checkable
class ArtifactStore(Protocol):
    """One result, put somewhere it can be read back."""

    async def put(self, *, org_id: uuid.UUID, execution_id: uuid.UUID, payload: bytes) -> str:
        """Write, and return the reference that finds it again."""
        ...

    async def get(self, *, org_id: uuid.UUID, reference: str) -> bytes | None:
        """Read it back, or None if it is gone — expired, swept, never written."""
        ...


class LocalArtifactStore:
    """Files under a directory. The development and single-node answer."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def put(self, *, org_id: uuid.UUID, execution_id: uuid.UUID, payload: bytes) -> str:
        reference = f"{org_id}/{execution_id}.json"
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
            raise StoredArtifactError("That artifact belongs to another organization.")
        # Resolved and re-checked, so a reference carrying `..` cannot climb out of the root...
        candidate = (self._root / reference).resolve()
        root = self._root.resolve()
        if not candidate.is_relative_to(root / str(org_id)):
            raise StoredArtifactError("That artifact reference is not a valid one.")
        return candidate


class BlobArtifactStore:
    """Azure Blob Storage. The deployed answer (WP12.2, architecture 6.4)."""

    def __init__(
        self,
        *,
        account_url: str,
        container: str,
        client: object | None = None,
    ) -> None:
        if not account_url:
            raise StoredArtifactError(
                "ARTIFACTS_BACKEND=blob needs ARTIFACTS_ACCOUNT_URL. The deployment "
                "sets it from the storage account the Bicep created."
            )
        self._container_name = container
        if client is not None:
            self._service = client
            return
        # Deferred for the reason `secrets/keyvault.py` defers its own.
        from azure.identity.aio import DefaultAzureCredential
        from azure.storage.blob.aio import BlobServiceClient

        # The credential is held rather than passed inline so `aclose` can close it.
        self._credential: object = DefaultAzureCredential()
        self._service = BlobServiceClient(account_url=account_url, credential=self._credential)

    async def aclose(self) -> None:
        """Release the connection pools this store holds."""
        for holder in (self._service, self._credential):
            close = getattr(holder, "close", None)
            if close is not None:
                with suppress(Exception):
                    await close()

    def _blob(self, reference: str) -> Any:
        service = cast(Any, self._service)
        return service.get_blob_client(container=self._container_name, blob=reference)

    async def put(self, *, org_id: uuid.UUID, execution_id: uuid.UUID, payload: bytes) -> str:
        reference = f"{org_id}/{execution_id}.json"
        await self._blob(reference).upload_blob(payload, overwrite=True)
        return reference

    async def get(self, *, org_id: uuid.UUID, reference: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        self._check_tenant(org_id, reference)
        try:
            stream = await self._blob(reference).download_blob()
            return cast(bytes, await stream.readall())
        except ResourceNotFoundError:
            return None

    @staticmethod
    def _check_tenant(org_id: uuid.UUID, reference: str) -> None:
        """Refuse a reference belonging to another organization."""
        if not reference.startswith(f"{org_id}/"):
            raise StoredArtifactError("That artifact belongs to another organization.")


def artifact_store(settings: Settings | None = None) -> ArtifactStore:
    """The store this deployment uses."""
    resolved = settings if settings is not None else get_settings()
    if resolved.artifacts_backend == "blob":
        return BlobArtifactStore(
            account_url=resolved.artifacts_account_url or "",
            container=resolved.artifacts_container,
        )
    return LocalArtifactStore(resolved.artifacts_path)


def summarize(frame: MaskedFrame) -> dict[str, object]:
    """The shape of a result, with none of its values."""
    return {
        "columns": list(frame.columns),
        "row_count": frame.row_count,
        "truncated": frame.truncated,
        "masked_columns": list(frame.masked_columns),
        "duration_ms": frame.duration_ms,
    }


def expires_at(settings: Settings | None = None, *, now: datetime | None = None) -> datetime:
    resolved = settings if settings is not None else get_settings()
    moment = now if now is not None else datetime.now(UTC)
    return moment + timedelta(days=resolved.artifact_retention_days)


#: The version of this artifact's envelope.
ARTIFACT_FORMAT = 2

#: What a column holds, recorded by the writer that still has the Python objects rather than...
ColumnType = Literal["number", "temporal", "text"]


def column_type(values: Iterable[object]) -> ColumnType:
    """What this column holds, from the values as the driver returned them."""
    present = [value for value in values if value is not None]
    if not present:
        return "text"
    if all(
        isinstance(value, int | float | Decimal) and not isinstance(value, bool)
        for value in present
    ):
        return "number"
    if all(isinstance(value, date | datetime) for value in present):
        return "temporal"
    return "text"


def encode(frame: MaskedFrame) -> bytes:
    """The whole (masked) result, as JSON."""
    return json.dumps(
        {
            "format": ARTIFACT_FORMAT,
            "columns": list(frame.columns),
            "column_types": [
                column_type(row[index] for row in frame.rows if index < len(row))
                for index in range(len(frame.columns))
            ],
            "rows": [[encodable(value) for value in row] for row in frame.rows],
            "truncated": frame.truncated,
            "masked_columns": list(frame.masked_columns),
        },
        separators=(",", ":"),
    ).encode()


def encodable(value: object) -> object:
    """Whatever a driver handed back, as something JSON can hold."""
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        return _readable_float(value)
    return str(value)


#: Significant digits kept when a float is written down (B-179).
SIGNIFICANT_DIGITS = 12


def _readable_float(value: float) -> float:
    """The same number without its representation error."""
    if value != value or value in (float("inf"), float("-inf")):
        return value
    return float(f"{value:.{SIGNIFICANT_DIGITS}g}")
