"""remember and recall tools."""

from __future__ import annotations

from typing import Any

from app.memory.store import recall, remember
from app.models import User
from app.tools.base import Tool, ToolContext, ToolResult


class RememberTool(Tool):
    name = "remember"
    description = "ذخیرهٔ یک واقعیت ماندگار دربارهٔ سرنخ، مشتری، تأمین‌کننده یا موضوع کلی."
    provider = "pgvector"
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "entity_type": {"type": "string", "enum": ["lead", "customer", "supplier", "general"]},
            "entity_id": {"type": "string"},
            "importance": {"type": "integer"},
        },
        "required": ["content"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        content = str(arguments.get("content") or "").strip()
        if not content:
            return ToolResult(ok=False, content="متن حافظه خالی است.")
        row = remember(
            context.db,
            content=content,
            user_id=context.user_id,
            agent_type=context.agent_slug or "",
            entity_type=str(arguments.get("entity_type") or "general"),
            entity_id=str(arguments.get("entity_id") or "") or None,
            importance=int(arguments.get("importance") or 1),
            task_id=context.task_id,
        )
        return ToolResult(ok=True, content="در حافظه ذخیره شد.", data={"id": row.id})


class RecallTool(Tool):
    name = "recall"
    description = "یادآوری واقعیت‌های مرتبط از حافظهٔ بلندمدت."
    provider = "pgvector"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "entity_type": {"type": "string"},
            "entity_id": {"type": "string"},
            "k": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده در دسترس نیست.")
        user = context.db.get(User, context.user_id) if context.user_id else None
        rows = recall(
            context.db,
            query=str(arguments.get("query") or ""),
            user=user,
            user_id=context.user_id,
            agent_type=context.agent_slug or "",
            entity_type=str(arguments.get("entity_type") or "") or None,
            entity_id=str(arguments.get("entity_id") or "") or None,
            k=int(arguments.get("k") or 5),
            task_id=context.task_id,
        )
        if not rows:
            return ToolResult(ok=True, content="چیزی در حافظه پیدا نشد.", data={"memories": []})
        lines = [f"- ({row.entity_type}) {row.content[:400]}" for row in rows]
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={"memories": [{"id": row.id, "entity_type": row.entity_type} for row in rows]},
        )
