"""Three staff roles and the records each one may see."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, AgentTask, ApprovalRequest, Lead, User

ADMIN = "admin"
SALES = "sales"
SUPPLIER = "supplier_acquisition"
STAFF = frozenset({ADMIN, SALES, SUPPLIER})

SALES_AGENTS = frozenset({"lead_generation", "sales_negotiation"})
SUPPLIER_AGENTS = frozenset({"research", "consulting"})


def agent_slugs_for(role: str) -> frozenset[str] | None:
    """None means every agent. An empty set means none."""
    if role == ADMIN:
        return None
    if role == SALES:
        return SALES_AGENTS
    if role == SUPPLIER:
        return SUPPLIER_AGENTS
    return frozenset()


def agent_allowed(user: User, slug: str) -> bool:
    allowed = agent_slugs_for(user.role)
    if allowed is None:
        return True
    return slug in allowed


def require_agent(user: User, agent: Agent | None) -> Agent:
    if agent is None or not agent.is_active:
        raise HTTPException(status_code=404, detail="عامل پیدا نشد")
    if not agent_allowed(user, agent.slug):
        raise HTTPException(status_code=403, detail="این عامل برای نقش شما در دسترس نیست")
    return agent


def party_for_role(role: str) -> str | None:
    if role == SALES:
        return "customer"
    if role == SUPPLIER:
        return "supplier"
    return None


def lead_visible(user: User, lead: Lead) -> bool:
    if user.role == ADMIN:
        return True
    expected = party_for_role(user.role)
    return expected is not None and lead.party == expected


def task_visible(db: Session, user: User, task: AgentTask) -> bool:
    if user.role == ADMIN:
        return True
    owner = db.get(User, task.user_id)
    if owner is None or owner.role != user.role:
        return False
    if not task.agent_id:
        return True
    agent = db.get(Agent, task.agent_id)
    if agent is None:
        return True
    return agent_allowed(user, agent.slug)


def can_decide_approval(db: Session, user: User, row: ApprovalRequest) -> bool:
    if user.role == ADMIN:
        return True
    if user.role not in STAFF:
        return False
    if row.requested_by:
        requester = db.get(User, row.requested_by)
        if requester is not None and requester.role == user.role:
            if row.agent_id:
                agent = db.get(Agent, row.agent_id)
                if agent is not None and not agent_allowed(user, agent.slug):
                    return False
            return True
    if row.task_id:
        task = db.get(AgentTask, row.task_id)
        if task is not None and task_visible(db, user, task):
            return True
    return False


def team_user_ids(db: Session, user: User):
    if user.role == ADMIN:
        return select(User.id)
    return select(User.id).where(User.role == user.role)
