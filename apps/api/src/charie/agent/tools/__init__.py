"""The tools the agent may call (architecture Part 4.6).

``registry`` is the gate: it decides which tools a caller may see, validates
arguments before dispatch, and wraps every result in a typed envelope. Nothing
calls a handler directly, for the same reason nothing calls ``executor.execute``
directly — the gate is where the properties live.
"""

from __future__ import annotations

from charie.agent.tools.base import (
    Tool,
    ToolContext,
    ToolError,
    ToolResult,
    UnknownToolError,
)
from charie.agent.tools.registry import ToolRegistry, default_registry

__all__ = [
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "UnknownToolError",
    "default_registry",
]
