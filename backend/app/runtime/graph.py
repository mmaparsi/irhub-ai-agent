"""One autonomous loop shared by every specialist.

The graph plans, calls tools, observes the results, and repeats until the
model stops or the step budget is spent. Outbound tools call interrupt() so
the Postgres checkpointer can resume after a human approval.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.models import AgentTask
from app.runtime.context import RunContext, run_context
from app.runtime.events import emit_event
from app.runtime.gates import run_gated_tool
from app.runtime.llm import complete
from app.tools.base import ToolContext, ToolResult, tool_registry

logger = logging.getLogger(__name__)


class AgentRunState(TypedDict, total=False):
    goal: str
    plan: str
    report: str
    messages: list[dict]
    step: int
    max_steps: int
    status: str
    model: str
    fast_model: str
    temperature: float
    allowed_tools: list[str]
    system_prompt: str
    agent_name: str


def build_agent_graph(checkpointer: object):
    graph = StateGraph(AgentRunState)
    graph.add_node("plan", plan_node)
    graph.add_node("actor", actor_node)
    graph.add_node("tools", tools_node)
    graph.add_node("report", report_node)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", after_plan, {"actor": "actor", "end": END})
    graph.add_conditional_edges(
        "actor", after_actor, {"tools": "tools", "report": "report", "end": END}
    )
    graph.add_conditional_edges(
        "tools", after_tools, {"actor": "actor", "report": "report", "end": END}
    )
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


async def plan_node(state: AgentRunState) -> dict:
    ctx = run_context.get()
    if _stopped(ctx.db, ctx.task_id):
        return {"status": "stopped", "report": "اجرای وظیفه توسط کاربر متوقف شد."}
    result = await complete(
        phase="plan",
        messages=[
            {
                "role": "system",
                "content": state["system_prompt"]
                + "\nاول فقط یک برنامهٔ کوتاه و شماره‌دار به فارسی بنویس. ابزار را صدا نزن.",
            },
            {"role": "user", "content": state["goal"]},
        ],
        tools=None,
        model=state["model"],
        fast_model=state["fast_model"],
        temperature=state.get("temperature") or 0.2,
    )
    plan = (result.get("content") or "").strip()
    emit_event(ctx.db, ctx.task_id, "plan", {"text": plan}, dedupe_key=f"{ctx.thread_id}:plan")
    messages = [
        {
            "role": "system",
            "content": (
                f"{state['system_prompt']}\n"
                "طبق برنامه با ابزارها کار کن. داده را جعل نکن. "
                "وقتی هدف انجام شد، بدون ابزار جمع‌بندی کن.\n"
                f"برنامه:\n{plan}"
            ),
        },
        {"role": "user", "content": state["goal"]},
    ]
    return {"plan": plan, "messages": messages, "step": 0, "status": "running"}


async def actor_node(state: AgentRunState) -> dict:
    ctx = run_context.get()
    if _stopped(ctx.db, ctx.task_id):
        return {
            "status": "stopped",
            "report": state.get("report") or "اجرای وظیفه توسط کاربر متوقف شد.",
        }
    step = int(state.get("step") or 0) + 1
    if step > int(state.get("max_steps") or 12):
        return {"step": step, "status": "budget"}
    schemas = _schemas(state.get("allowed_tools") or [])
    result = await complete(
        phase="act",
        messages=list(state.get("messages") or []),
        tools=schemas or None,
        model=state["model"],
        fast_model=state["fast_model"],
        temperature=state.get("temperature") or 0.2,
    )
    message = {
        "role": "assistant",
        "content": result.get("content") or "",
        "tool_calls": result.get("tool_calls") or [],
    }
    emit_event(
        ctx.db,
        ctx.task_id,
        "action",
        {
            "step": step,
            "content": message["content"],
            "tools": [c.get("name") for c in message["tool_calls"]],
        },
        dedupe_key=f"{ctx.thread_id}:action:{step}",
    )
    return {
        "messages": list(state.get("messages") or []) + [message],
        "step": step,
        "status": "running",
    }


async def tools_node(state: AgentRunState) -> dict:
    ctx = run_context.get()
    if _stopped(ctx.db, ctx.task_id):
        return {"status": "stopped"}
    last = (state.get("messages") or [])[-1]
    allowed = set(state.get("allowed_tools") or [])
    outputs: list[dict] = []
    for call in last.get("tool_calls") or []:
        result = await _run_tool(call, allowed, ctx)
        emit_event(
            ctx.db,
            ctx.task_id,
            "tool_call",
            {
                "name": call.get("name"),
                "arguments": call.get("arguments"),
                "step": state.get("step"),
            },
            dedupe_key=f"{ctx.thread_id}:call:{call.get('id')}",
        )
        emit_event(
            ctx.db,
            ctx.task_id,
            "tool_result",
            {
                "name": call.get("name"),
                "ok": result.ok,
                "content": result.content[:4000],
                "step": state.get("step"),
            },
            dedupe_key=f"{ctx.thread_id}:result:{call.get('id')}",
        )
        outputs.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id"),
                "name": call.get("name"),
                "content": clean_tool_text(result.content),
            }
        )
    messages = trim_tool_history(list(state.get("messages") or []) + outputs)
    return {"messages": messages}


async def report_node(state: AgentRunState) -> dict:
    ctx = run_context.get()
    if state.get("status") == "stopped":
        return {
            "report": state.get("report") or "اجرای وظیفه توسط کاربر متوقف شد.",
            "status": "stopped",
        }
    result = await complete(
        phase="report",
        messages=list(state.get("messages") or [])
        + [{"role": "user", "content": "گزارش نهایی را به فارسی، با یافته‌ها و محدودیت‌ها، بنویس."}],
        tools=None,
        model=state["model"],
        fast_model=state["fast_model"],
        temperature=state.get("temperature") or 0.2,
    )
    report = (result.get("content") or "").strip()
    emit_event(
        ctx.db, ctx.task_id, "report", {"text": report}, dedupe_key=f"{ctx.thread_id}:report"
    )
    return {"report": report, "status": "completed"}


def after_plan(state: AgentRunState) -> str:
    if state.get("status") == "stopped":
        return "end"
    return "actor"


def after_actor(state: AgentRunState) -> str:
    if state.get("status") == "stopped":
        return "end"
    if state.get("status") == "budget":
        return "report"
    last = (state.get("messages") or [{}])[-1]
    if last.get("tool_calls"):
        return "tools"
    return "report"


def after_tools(state: AgentRunState) -> str:
    if state.get("status") == "stopped":
        return "end"
    if int(state.get("step") or 0) >= int(state.get("max_steps") or 12):
        return "report"
    return "actor"


async def _run_tool(call: dict, allowed: set[str], ctx: RunContext) -> ToolResult:
    name = call.get("name") or ""
    arguments = call.get("arguments") or {}
    if name not in allowed:
        return ToolResult(ok=False, content=f"ابزار {name} برای این عامل مجاز نیست.")
    try:
        tool = tool_registry.get(name)
    except KeyError:
        return ToolResult(ok=False, content=f"ابزار {name} ثبت نشده است.")
    context = ToolContext(
        user_id=ctx.user_id,
        agent_id=ctx.agent_id,
        agent_slug=ctx.agent_slug,
        task_id=ctx.task_id,
        thread_id=ctx.thread_id,
        db=ctx.db,
    )
    try:
        if name == "delegate" and hasattr(tool, "aexecute"):
            return await tool.aexecute(arguments, context)
        if getattr(tool, "kind", "") == "outbound":
            return run_gated_tool(tool, arguments, context, str(call.get("id") or name))
        return tool.execute(arguments, context)
    except Exception as exc:
        from langgraph.errors import GraphInterrupt

        if isinstance(exc, GraphInterrupt):
            raise
        logger.exception("tool %s failed", name)
        return ToolResult(ok=False, content=f"اجرای {name} ناموفق بود: {exc}")


_TOOL_TEXT_LIMIT = 6000
_TOOL_HISTORY_BUDGET = 24000


def clean_tool_text(text: str, limit: int = _TOOL_TEXT_LIMIT) -> str:
    """Drop control and surrogate characters, then cap the tool message."""
    kept: list[str] = []
    for char in text or "":
        code = ord(char)
        if char in "\n\r\t":
            kept.append(char)
            continue
        if code < 32 or 0xD800 <= code <= 0xDFFF:
            continue
        kept.append(char)
    cleaned = "".join(kept)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "\n[truncated]"


def trim_tool_history(messages: list[dict], budget: int = _TOOL_HISTORY_BUDGET) -> list[dict]:
    """Shrink the oldest tool outputs once their combined size exceeds the budget."""
    updated = [dict(item) for item in messages]
    indexes = [index for index, item in enumerate(updated) if item.get("role") == "tool"]
    total = sum(len(str(updated[index].get("content") or "")) for index in indexes)
    for index in indexes:
        if total <= budget:
            break
        content = str(updated[index].get("content") or "")
        if len(content) <= 400:
            continue
        shortened = content[:400] + "\n[truncated]"
        total -= len(content) - len(shortened)
        updated[index]["content"] = shortened
    return updated


def _schemas(names: list[str]) -> list[dict]:
    schemas = []
    for name in names:
        try:
            schemas.append(tool_registry.get(name).to_llm_tool())
        except KeyError:
            continue
    return schemas


def _stopped(db: Session, task_id: str) -> bool:
    db.commit()
    task = db.get(AgentTask, task_id)
    if task is None:
        return False
    db.refresh(task)
    return task.status in {"stopping", "stopped"}
