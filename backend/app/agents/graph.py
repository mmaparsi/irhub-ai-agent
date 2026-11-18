from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.runner import iter_turn
from app.agents.supervisor import route_task
from app.database import open_session
from app.models import Agent, Conversation, Message

logger = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    task: str
    agent_slug: str
    user_id: str
    conversation_id: str
    tier: str
    history: list[dict[str, str]]
    result: str
    approval_ids: list[str]


def build_supervisor_graph(specialist):
    """One supervisor node and one specialist node.

    Specialists are not hard-coded graph nodes. The specialist callable loads
    whichever agent the registry (and the database row) describes, so adding
    an agent does not require a new edge.
    """

    def supervisor_node(state: GraphState) -> dict[str, str]:
        return {"agent_slug": route_task(state.get("task", ""), state.get("agent_slug"))}

    graph = StateGraph(GraphState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("specialist", specialist)
    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "specialist")
    graph.add_edge("specialist", END)
    return graph.compile()


def next_seq(db, conversation_id: str) -> int:
    from sqlalchemy import func

    current = db.scalar(
        select(func.max(Message.seq)).where(Message.conversation_id == conversation_id)
    )
    return int(current or 0) + 1


async def real_specialist_node(state: GraphState) -> dict[str, Any]:
    db = open_session()
    try:
        slug = state.get("agent_slug") or ""
        agent = db.scalar(select(Agent).where(Agent.slug == slug, Agent.is_active.is_(True)))
        if agent is None:
            return {
                "result": "عامل فعالی برای این کار پیدا نشد.",
                "approval_ids": [],
                "agent_slug": slug,
            }
        conversation_id = state.get("conversation_id")
        if conversation_id:
            conversation = db.get(Conversation, conversation_id)
            if conversation is not None and conversation.agent_id is None:
                conversation.agent_id = agent.id
            db.add(
                Message(
                    conversation_id=conversation_id,
                    seq=next_seq(db, conversation_id),
                    role="user",
                    content=state.get("task") or "",
                )
            )
            db.flush()
        parts: list[str] = []
        approvals: list[str] = []
        async for kind, payload in iter_turn(
            db,
            agent=agent,
            history=list(state.get("history") or []),
            user_text=state.get("task") or "",
            tier=state.get("tier") or "strong",
            user_id=state.get("user_id"),
            conversation_id=conversation_id,
        ):
            if kind == "token":
                parts.append(str(payload))
            elif kind == "approval" and payload:
                approvals.append(str(payload))
        text = "".join(parts)
        if conversation_id:
            db.add(
                Message(
                    conversation_id=conversation_id,
                    seq=next_seq(db, conversation_id),
                    role="assistant",
                    content=text,
                )
            )
        db.commit()
        return {"result": text, "approval_ids": approvals, "agent_slug": slug}
    except Exception:
        db.rollback()
        logger.exception("specialist node failed")
        raise
    finally:
        db.close()


def get_compiled_graph():
    return build_supervisor_graph(real_specialist_node)
