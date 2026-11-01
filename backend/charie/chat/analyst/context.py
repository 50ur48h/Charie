"""What one running question carries (P10.1). Later sub-phases add fields."""

import asyncio
import time
from dataclasses import dataclass, field

from charie.chat.analyst.stream import ThinkingLog


@dataclass
class RunState:
    """Stop flag and start time for one running question."""

    finish_requested: asyncio.Event = field(default_factory=asyncio.Event)
    started: float = field(default_factory=time.monotonic)


@dataclass
class AnalystContext:
    """Everything the analyst needs for one assistant message."""

    message_id: int
    chat_id: int
    question: str
    kb_version_id: int
    data_through: object
    settings: dict
    log: ThinkingLog
    state: RunState
    private: bool = False
