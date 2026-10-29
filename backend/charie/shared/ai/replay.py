"""Replays: record real replies once, reuse them for $0 (architecture 08)."""

import hashlib
import json
from pathlib import Path
from typing import Any

from charie.shared.ai.errors import AiReplayMissing


def fingerprint(request: dict[str, Any]) -> str:
    """The SHA-256 of the sorted, compact JSON of 03's 4 parts."""
    parts = {
        "model": request["model"],
        "messages": request["messages"],
        "schema": request["schema"],
        "reasoning_effort": request["reasoning_effort"],
    }
    compact = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


class ReplayStore:
    """`<dir>/<job>/<fingerprint>.json` files with content and usage numbers."""

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)

    def path_for(self, job: str, digest: str) -> Path:
        return self.folder / job / f"{digest}.json"

    def save(self, job: str, digest: str, record: dict[str, Any]) -> None:
        path = self.path_for(job, digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, job: str, digest: str) -> dict[str, Any]:
        path = self.path_for(job, digest)
        if not path.exists():
            raise AiReplayMissing(job, digest)
        return json.loads(path.read_text(encoding="utf-8"))


def default_dir() -> Path:
    """`AI_REPLAY_DIR`, or the tests folder; relative paths count from the repo."""
    from charie.shared.config import get_settings

    raw = get_settings().ai_replay_dir or "backend/tests/replays/"
    folder = Path(raw)
    if not folder.is_absolute():
        folder = Path(__file__).resolve().parents[4] / folder
    return folder
