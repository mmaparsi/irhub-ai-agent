from __future__ import annotations

from typing import Any

from app.rules.business import BusinessRuleError
from app.tools.base import Tool, ToolContext, ToolResult, tool_registry
from app.tools.providers import get_crm_provider


class WebSearchTool(Tool):
    name = "web_search"
    description = "جست‌وجوی وب از طریق SearXNG، و در صورت تنظیم کلید از Tavily یا Brave."
    provider = "searxng"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "عبارت جست‌وجو"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        from app.tools.search import search_web

        try:
            results = search_web(str(arguments["query"]), limit=int(arguments.get("limit") or 5))
        except Exception as exc:
            return ToolResult(ok=False, content=f"جست‌وجوی وب ناموفق بود: {exc}")
        if not results:
            return ToolResult(ok=True, content="نتیجه‌ای پیدا نشد.", data={"results": []})
        lines = [f"- {item['title']}: {item['snippet']} ({item['url']})" for item in results]
        return ToolResult(ok=True, content="\n".join(lines), data={"results": results})


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "دریافت و پاک‌سازی متن یک صفحهٔ وب."
    provider = "httpx"
    input_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        from app.tools.fetch import fetch_page

        try:
            page = fetch_page(str(arguments["url"]))
        except Exception as exc:
            return ToolResult(ok=False, content=f"دریافت صفحه ناموفق بود: {exc}")
        content = f"{page.get('title')}\n{page.get('text')}"
        return ToolResult(ok=True, content=content, data=page)


class KnowledgeSearchTool(Tool):
    name = "knowledge_search"
    description = "جست‌وجو در پایگاه دانش داخلی شرکت."
    provider = "pgvector"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده برای جست‌وجوی دانش در دسترس نیست.")
        from app.knowledge.search import search_documents

        limit = max(1, min(int(arguments.get("limit") or 5), 10))
        found = search_documents(context.db, str(arguments["query"]), limit=limit)
        if not found:
            return ToolResult(
                ok=True, content="سندی در پایگاه دانش پیدا نشد.", data={"results": []}
            )
        lines = []
        payload = []
        for doc, distance in found:
            excerpt = doc.content[:280].replace("\n", " ")
            lines.append(f"- {doc.title}: {excerpt}")
            payload.append({"id": doc.id, "title": doc.title, "distance": distance})
        return ToolResult(ok=True, content="\n".join(lines), data={"results": payload})


class CrmLookupTool(Tool):
    name = "crm_lookup"
    description = "جست‌وجوی مخاطب در CRM. اتصال واقعی هنوز ساخته نشده است."
    provider = "placeholder"
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        data = get_crm_provider().lookup(str(arguments["query"]))
        return ToolResult(ok=True, content=str(data.get("note")), data=data)


class _OutboundTool(Tool):
    kind = "outbound"
    action_type = ""

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="برای ثبت تأیید به نشست پایگاه داده نیاز است.")
        from app.approvals.service import request_approval

        try:
            approval = request_approval(
                context.db,
                action_type=self.action_type,
                payload=arguments,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                agent_id=context.agent_id,
                task_id=context.task_id,
            )
        except BusinessRuleError as exc:
            return ToolResult(ok=False, content=exc.message, data={"code": exc.code})
        return ToolResult(
            ok=True,
            approval_required=True,
            approval_id=approval.id,
            content=(
                f"این اقدام ارسال نشد. درخواست تأیید برای کارشناس ثبت شد (شناسه {approval.id})."
            ),
            data={"approval_id": approval.id, "status": "pending"},
        )


class SendEmailTool(_OutboundTool):
    name = "send_email"
    action_type = "email"
    description = "ثبت پیش‌نویس ایمیل برای تأیید کارشناس. ایمیل را مستقیم ارسال نمی‌کند."
    input_schema = {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
        "additionalProperties": False,
    }


class SendMessageTool(_OutboundTool):
    name = "send_message"
    action_type = "message"
    description = "ثبت پیش‌نویس پیام (پیامک یا پیام‌رسان) برای تأیید کارشناس."
    input_schema = {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "to": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "body"],
        "additionalProperties": False,
    }


class ProposePriceTool(_OutboundTool):
    name = "propose_price"
    action_type = "price_offer"
    description = "ثبت پیشنهاد قیمت برای تأیید کارشناس. سقف تخفیف در کد اعمال می‌شود."
    input_schema = {
        "type": "object",
        "properties": {
            "deal_title": {"type": "string"},
            "amount": {"type": "number"},
            "currency": {"type": "string"},
            "discount_percent": {"type": "number"},
            "note": {"type": "string"},
        },
        "required": ["deal_title", "discount_percent"],
        "additionalProperties": False,
    }


def register_builtin_tools() -> None:
    from app.tools.actions import (
        BrowserTool,
        CreateLeadTool,
        DelegateTool,
        ExportLeadsTool,
        MemorySaveTool,
        MemorySearchTool,
        PythonExecTool,
        SearchLeadsTool,
        UpdateLeadTool,
        WriteReportTool,
    )

    for tool in (
        WebSearchTool(),
        WebFetchTool(),
        KnowledgeSearchTool(),
        CrmLookupTool(),
        SendEmailTool(),
        SendMessageTool(),
        ProposePriceTool(),
        CreateLeadTool(),
        UpdateLeadTool(),
        SearchLeadsTool(),
        ExportLeadsTool(),
        MemorySaveTool(),
        MemorySearchTool(),
        WriteReportTool(),
        PythonExecTool(),
        BrowserTool(),
        DelegateTool(),
    ):
        tool_registry.ensure(tool)


register_builtin_tools()
