"""Job handlers register here; the runner looks them up by kind."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobInfo:
    """What the runner hands a handler."""

    id: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: int | None = None
    attempts: int = 1


HANDLERS: dict[str, Callable[[JobInfo], None]] = {}


def job_handler(kind: str):
    """Register the handler for one job kind; registering twice is refused."""

    def register(handler: Callable[[JobInfo], None]):
        if kind in HANDLERS:
            raise ValueError(f"Job kind `{kind}` has two handlers.")
        HANDLERS[kind] = handler
        return handler

    return register
