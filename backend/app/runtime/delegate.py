"""Run a specialist graph as a child checkpoint of the current task."""

from __future__ import annotations

from langgraph.types import Command, interrupt

from app.models import Agent
from app.runtime.context import RunContext, run_context
from app.runtime.graph import build_agent_graph


async def run_delegated(*, agent_slug: str, goal: str, context) -> str:
    parent = run_context.get()
    db = parent.db
    agent = (
        db.query(Agent).filter(Agent.slug == agent_slug, Agent.is_active.is_(True)).one_or_none()
    )
    if agent is None:
        return f"عامل فعالی با شناسه {agent_slug} پیدا نشد."
    thread_id = f"{parent.thread_id}:del:{agent_slug}:{abs(hash(goal)) % 100000}"
    graph = build_agent_graph(parent.saver)
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
    child = RunContext(
        db=db,
        task_id=parent.task_id,
        user_id=parent.user_id,
        agent_id=agent.id,
        agent_slug=agent.slug,
        thread_id=thread_id,
        saver=parent.saver,
        depth=parent.depth + 1,
        budget=max(2, min(parent.budget, 6)),
    )
    token = run_context.set(child)
    try:
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            await graph.ainvoke(_initial(agent, goal), config)
            snapshot = await graph.aget_state(config)
        while snapshot.interrupts:
            decision = interrupt(snapshot.interrupts[0].value)
            await graph.ainvoke(Command(resume=decision), config)
            snapshot = await graph.aget_state(config)
        if snapshot.next and not snapshot.interrupts:
            await graph.ainvoke(None, config)
            snapshot = await graph.aget_state(config)
        return str(snapshot.values.get("report") or "")
    finally:
        run_context.reset(token)


def _initial(agent: Agent, goal: str) -> dict:
    return {
        "goal": goal,
        "plan": "",
        "report": "",
        "messages": [],
        "step": 0,
        "max_steps": 6,
        "status": "running",
        "model": agent.model_strong,
        "fast_model": agent.model_fast,
        "temperature": agent.temperature,
        "allowed_tools": [name for name in (agent.allowed_tools or []) if name != "delegate"],
        "system_prompt": agent.system_prompt,
        "agent_name": agent.name_fa,
    }
