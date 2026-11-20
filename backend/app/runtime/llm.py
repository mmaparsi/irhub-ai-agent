"""LLM adapter for the autonomous loop, including a deterministic mock."""

from __future__ import annotations

import contextvars
from typing import Any

from app.agents.llm import stream_model
from app.config import settings
from app.runtime.context import run_context
from app.runtime.events import emit_event

scripted_llm: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar(
    "scripted_llm", default=None
)


async def complete(
    *,
    phase: str,
    messages: list[dict],
    tools: list[dict] | None,
    model: str,
    fast_model: str,
    temperature: float,
) -> dict[str, Any]:
    script = scripted_llm.get()
    if script:
        return script.pop(0)
    if settings.llm_is_mock():
        return _mock(phase, messages, tools or [])
    chunks: list[str] = []
    calls: list[dict[str, Any]] = []

    def notify(kind: str, payload: dict[str, Any]) -> None:
        _task_emit(kind, {"phase": phase, **payload})

    async for kind, payload in stream_model(
        model=model,
        fast_model=fast_model,
        messages=messages,
        temperature=temperature,
        tools=tools,
        notify=notify,
    ):
        if kind == "token" and payload:
            chunks.append(str(payload))
            _task_emit("token", {"text": str(payload), "phase": phase})
        elif kind == "tools":
            calls = list(payload or [])
    return {"content": "".join(chunks), "tool_calls": calls}


def _task_emit(kind: str, payload: dict[str, Any]) -> None:
    try:
        ctx = run_context.get()
    except LookupError:
        return
    if ctx.db is None or not ctx.task_id:
        return
    emit_event(ctx.db, ctx.task_id, kind, payload)


def _mock(phase: str, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
    names = [item.get("function", {}).get("name") for item in tools]
    if phase == "plan":
        return {
            "content": "برنامه: داده را با ابزار جمع کن، نتیجه را ثبت کن، بعد گزارش بده.",
            "tool_calls": [],
        }
    if phase == "report":
        notes = [item.get("content") or "" for item in messages if item.get("role") == "tool"]
        body = "\n".join(notes)[:2000] or "ابزاری اجرا نشد."
        return {"content": f"گزارش نهایی:\n{body}", "tool_calls": []}
    if any(item.get("role") == "tool" for item in messages):
        return {"content": "اطلاعات کافی جمع شد.", "tool_calls": []}
    goal = ""
    for item in messages:
        if item.get("role") == "user":
            goal = item.get("content") or ""
    if "create_lead" in names and any(word in goal for word in ("ثبت", "سرنخ")):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "mock-create_lead",
                    "name": "create_lead",
                    "arguments": _mock_args("create_lead", messages),
                }
            ],
        }
    for preferred in ("web_search", "search_leads", "knowledge_search", "create_lead"):
        if preferred in names:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": f"mock-{preferred}",
                        "name": preferred,
                        "arguments": _mock_args(preferred, messages),
                    }
                ],
            }
    return {"content": "کاری برای ابزارهای مجاز نمانده است.", "tool_calls": []}


def _mock_args(name: str, messages: list[dict]) -> dict:
    goal = ""
    for item in messages:
        if item.get("role") == "user":
            goal = item.get("content") or ""
    if name == "web_search":
        return {"query": goal[:200] or "تولیدکنندگان", "limit": 5}
    if name == "search_leads":
        return {"query": goal[:80] or "تهران"}
    if name == "knowledge_search":
        return {"query": goal[:80] or "محصول"}
    return {
        "company_name": "تولیدی نمونه تهران",
        "title": (goal[:80] or "سرنخ جدید"),
        "city": "تهران",
        "notes": "ثبت‌شده توسط حالت آزمایشی",
    }
