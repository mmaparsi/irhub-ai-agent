from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session


@dataclass
class ToolContext:
    user_id: str | None = None
    conversation_id: str | None = None
    agent_id: str | None = None
    agent_slug: str | None = None
    db: Session | None = None


@dataclass
class ToolResult:
    ok: bool
    content: str
    data: dict[str, Any] | None = None
    approval_required: bool = False
    approval_id: str | None = None


class Tool(ABC):
    """MCP-compatible tool.

    `to_mcp_tool()` matches an MCP `tools/list` item (`name`, `description`,
    `inputSchema`). Agents depend on this interface, not on a transport.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    kind: str = "read"
    provider: str = "stub"

    @abstractmethod
    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raise NotImplementedError

    def to_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

    def to_llm_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


def missing_required(schema: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    required = schema.get("required") or []
    return [key for key in required if arguments.get(key) in (None, "")]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def ensure(self, tool: Tool) -> None:
        if tool.name not in self._tools:
            self.register(tool)

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)

    def list(self) -> list[Tool]:
        return [self._tools[name] for name in self.names()]

    def for_names(self, names: list[str]) -> list[Tool]:
        return [self._tools[name] for name in names if name in self._tools]


tool_registry = ToolRegistry()
