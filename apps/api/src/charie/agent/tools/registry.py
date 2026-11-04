"""The gate every tool call goes through (architecture Part 4.6)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import ValidationError

from charie.agent.tools.base import Tool, ToolContext, ToolError, ToolResult, UnknownToolError
from charie.auth.guards import ADMIN_ONLY, ANY_MEMBER, CONTRIBUTOR_OR_ADMIN
from charie.runs.events import EventWriter

__all__ = ["ToolRegistry", "default_registry"]

#: Which roles satisfy each declared minimum.
_ROLES_SATISFYING: Mapping[str, tuple[str, ...]] = {
    "reader": ANY_MEMBER,
    "contributor": CONTRIBUTOR_OR_ADMIN,
    "admin": ADMIN_ONLY,
}


class ToolRegistry:
    """A set of tools, and the only way to call one."""

    __slots__ = ("_tools",)

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"a tool named {tool.name!r} is already registered")
        if tool.required_role not in _ROLES_SATISFYING:
            raise ValueError(
                f"{tool.name!r} requires role {tool.required_role!r}, which is not one of "
                f"{sorted(_ROLES_SATISFYING)}"
            )
        self._tools[tool.name] = tool

    def available_to(self, role: str) -> tuple[Tool, ...]:
        """The tools this role may call, in registration order."""
        return tuple(
            tool for tool in self._tools.values() if role in _ROLES_SATISFYING[tool.required_role]
        )

    def describe_for(self, role: str) -> str:
        """The tool list as it is rendered into a prompt."""
        tools = self.available_to(role)
        if not tools:
            return "No tools are available to you."
        return "You may call these tools:\n" + "\n".join(tool.describe() for tool in tools)

    async def call(
        self,
        context: ToolContext,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        events: EventWriter | None = None,
    ) -> ToolResult:
        """Validate, dispatch, and come back with an envelope either way."""
        tool = self._tools.get(name)
        if tool is None or context.role not in _ROLES_SATISFYING[tool.required_role]:
            available = tuple(t.name for t in self.available_to(context.role))
            return await self._finish(
                events, ToolResult.failed(name, UnknownToolError(name, available))
            )

        raw = dict(arguments or {})
        try:
            params = tool.params.model_validate(raw)
        except ValidationError as error:
            return await self._finish(
                events,
                ToolResult.failed(
                    name,
                    ToolError(
                        f"arguments are not valid for {name}: {_readable(error)}",
                        code="invalid_arguments",
                        repairable=True,
                    ),
                    safe_args=_safe(raw),
                ),
            )

        if events is not None:
            # Emitted before dispatch, so a call that hangs or crashes is still visible in the...
            await events.emit("tool_called", {"tool": name, "safe_args": _safe(raw)})

        try:
            data = await tool.handler(context, params)
        except ToolError as error:
            return await self._finish(events, ToolResult.failed(name, error, safe_args=_safe(raw)))
        return await self._finish(events, ToolResult.succeeded(name, data, safe_args=_safe(raw)))

    async def _finish(self, events: EventWriter | None, result: ToolResult) -> ToolResult:
        """Record a failure in the trace; successes are described by their own tool's event."""
        if events is not None and not result.ok:
            await events.emit(
                "error",
                {"category": result.code or "tool_failed", "safe_message": result.error or ""},
            )
        return result


def _safe(arguments: Mapping[str, Any]) -> dict[str, object]:
    """Arguments as an event payload may carry them."""
    trimmed: dict[str, object] = {}
    for key, value in arguments.items():
        text = value if isinstance(value, str | int | float | bool | type(None)) else str(value)
        if isinstance(text, str) and len(text) > 500:
            text = text[:500] + "…"
        trimmed[key] = text
    return trimmed


def _readable(error: ValidationError) -> str:
    """A validation failure a model can act on."""
    parts = [
        f"{'.'.join(str(item) for item in problem['loc']) or '(root)'}: {problem['msg']}"
        for problem in error.errors()
    ]
    return "; ".join(parts[:5])


def default_registry() -> ToolRegistry:
    """The V1 tool set that WP7.2 needs, in the order a run tends to use them."""
    from charie.agent.tools.catalog import DESCRIBE_TABLE, SEARCH_TABLES
    from charie.agent.tools.chart import CREATE_CHART_SPEC
    from charie.agent.tools.knowledge import SEARCH_KNOWLEDGE
    from charie.agent.tools.sql import RUN_SQL

    return ToolRegistry(
        (SEARCH_TABLES, DESCRIBE_TABLE, SEARCH_KNOWLEDGE, RUN_SQL, CREATE_CHART_SPEC)
    )
