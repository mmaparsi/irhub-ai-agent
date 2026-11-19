from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import LLMCallError, classify_llm_error, persian_llm_error, stream_model
from app.config import settings
from app.models import Agent, ToolRecord
from app.tools.base import ToolContext, missing_required, tool_registry

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w.\-]+\.\w+")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|٪)")
_URL_RE = re.compile(r"https?://\S+")
_MAX_TOOL_ROUNDS = 3


def model_for(agent: Agent, tier: str) -> str:
    if tier == "fast":
        return agent.model_fast
    return agent.model_strong


def enabled_tool_names(db: Session) -> set[str] | None:
    rows = db.scalars(select(ToolRecord)).all()
    if not rows:
        return None
    return {row.name for row in rows if row.is_enabled}


def tools_for_agent(db: Session, agent: Agent) -> list:
    enabled = enabled_tool_names(db)
    names = list(agent.allowed_tools or [])
    if enabled is not None:
        names = [name for name in names if name in enabled]
    return tool_registry.for_names(names)


def plan_mock_tools(agent: Agent, user_text: str) -> list[tuple[str, dict[str, Any]]]:
    """Demo heuristic used only in mock mode so the UI can show tools and approvals.

    Real runs follow the model tool calls. This parser is not a business rule.
    """
    allowed = set(agent.allowed_tools or [])
    calls: list[tuple[str, dict[str, Any]]] = []
    if "web_search" in allowed and any(key in user_text for key in ("جستجو", "سرچ", "search")):
        calls.append(("web_search", {"query": user_text[:300]}))
    if "knowledge_search" in allowed and any(
        key in user_text for key in ("پایگاه دانش", "سند داخلی", "knowledge")
    ):
        calls.append(("knowledge_search", {"query": user_text[:300]}))
    if "crm_lookup" in allowed and any(key in user_text for key in ("CRM", "crm", "مخاطب")):
        calls.append(("crm_lookup", {"query": user_text[:300]}))
    if "web_fetch" in allowed:
        url_match = _URL_RE.search(user_text)
        if url_match:
            calls.append(("web_fetch", {"url": url_match.group(0).rstrip(").,")}))
    if "send_email" in allowed and any(key in user_text for key in ("ایمیل", "email")):
        email_match = _EMAIL_RE.search(user_text)
        if email_match:
            calls.append(
                (
                    "send_email",
                    {
                        "to": email_match.group(0),
                        "subject": "پیش‌نویس پیام",
                        "body": user_text[:4000],
                    },
                )
            )
    if "propose_price" in allowed and any(
        key in user_text for key in ("تخفیف", "پیشنهاد قیمت", "quote")
    ):
        percent = _PERCENT_RE.search(user_text)
        if percent:
            calls.append(
                (
                    "propose_price",
                    {
                        "deal_title": "پیشنهاد قیمت",
                        "amount": 0,
                        "currency": "IRR",
                        "discount_percent": float(percent.group(1)),
                        "note": user_text[:1000],
                    },
                )
            )
    return calls


def chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _mock_reply(agent: Agent, user_text: str, notes: list[str]) -> str:
    lines = [
        f"سلام، من {agent.name_fa} هستم.",
        "این پاسخ در حالت آزمایشی ساخته شده، چون کلید مدل زبانی تنظیم نشده است.",
        f"خلاصهٔ درخواست: {user_text.strip()[:400]}",
    ]
    if notes:
        lines.append("")
        lines.append("خروجی ابزارها:")
        lines.extend(notes)
    lines.append("")
    lines.append(
        "برای پاسخ واقعی، GEMINI_API_KEY یا ANTHROPIC_API_KEY یا OPENAI_API_KEY را قرار دهید و MOCK_LLM را خاموش کنید."
    )
    return "\n".join(lines)


def _execute_named(name: str, arguments: dict[str, Any], context: ToolContext, allowed: set[str]):
    if name not in allowed:
        from app.tools.base import ToolResult

        return ToolResult(ok=False, content=f"ابزار {name} برای این عامل مجاز نیست.")
    try:
        tool = tool_registry.get(name)
    except KeyError:
        from app.tools.base import ToolResult

        return ToolResult(ok=False, content=f"ابزار {name} ثبت نشده است.")
    missing = missing_required(tool.input_schema, arguments)
    if missing:
        from app.tools.base import ToolResult

        return ToolResult(ok=False, content="فیلدهای لازم ابزار کامل نیست: " + "، ".join(missing))
    try:
        return tool.execute(arguments, context)
    except Exception:
        logger.exception("tool %s failed", name)
        from app.tools.base import ToolResult

        return ToolResult(ok=False, content=f"اجرای ابزار {name} ناموفق بود.")


async def iter_turn(
    db: Session,
    *,
    agent: Agent,
    history: list[dict[str, str]],
    user_text: str,
    tier: str,
    user_id: str | None,
    conversation_id: str | None,
) -> AsyncIterator[tuple[str, Any]]:
    """Yield ('token', str) and ('approval', id) events."""
    context = ToolContext(
        user_id=user_id,
        conversation_id=conversation_id,
        agent_id=agent.id,
        agent_slug=agent.slug,
        db=db,
    )
    selected = tools_for_agent(db, agent)
    allowed = {tool.name for tool in selected}
    if settings.llm_is_mock():
        notes: list[str] = []
        for name, arguments in plan_mock_tools(agent, user_text):
            result = _execute_named(name, arguments, context, allowed)
            notes.append(f"[{name}] {result.content}")
            if result.approval_id:
                yield ("approval", result.approval_id)
        delay_chunks = chunk_text(_mock_reply(agent, user_text, notes))
        for part in delay_chunks:
            yield ("token", part)
        return

    messages: list[dict[str, Any]] = [{"role": "system", "content": agent.system_prompt}]
    for item in history[-20:]:
        if item.get("role") in {"user", "assistant"} and item.get("content"):
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_text})
    llm_tools = [tool.to_llm_tool() for tool in selected] or None

    for _round in range(_MAX_TOOL_ROUNDS):
        tool_calls: list[dict[str, Any]] = []
        try:
            async for kind, payload in stream_model(
                model=model_for(agent, tier),
                fast_model=agent.model_fast,
                messages=messages,
                temperature=agent.temperature,
                tools=llm_tools,
            ):
                if kind == "token":
                    yield ("token", payload)
                elif kind == "tools":
                    tool_calls = payload
        except LLMCallError as exc:
            logger.warning("llm chain failed reason=%s model=%s", exc.reason, exc.model)
            for part in chunk_text(exc.user_message):
                yield ("token", part)
            return
        except Exception as exc:
            logger.exception("llm call failed")
            message = persian_llm_error(classify_llm_error(exc), model_for(agent, tier))
            for part in chunk_text(message):
                yield ("token", part)
            return
        if not tool_calls:
            return
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                        },
                    }
                    for call in tool_calls
                ],
            }
        )
        stop_for_approval = False
        for call in tool_calls:
            result = _execute_named(call["name"], call["arguments"], context, allowed)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result.content})
            if result.approval_id:
                yield ("approval", result.approval_id)
            if result.approval_required or (
                not result.ok and result.data and result.data.get("code")
            ):
                for part in chunk_text("\n" + result.content):
                    yield ("token", part)
                if (
                    result.approval_required
                    or (result.data or {}).get("code") == "max_discount_exceeded"
                ):
                    stop_for_approval = True
        if stop_for_approval:
            return
    for part in chunk_text("\nبه سقف گام‌های ابزار رسیدم."):
        yield ("token", part)
