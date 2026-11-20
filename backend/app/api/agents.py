from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.registry import SLUG_RE
from app.audit import write_audit
from app.auth.deps import get_current_user, require_roles
from app.auth.rbac import agent_allowed, party_for_role
from app.config import settings
from app.database import get_db
from app.models import Agent, AgentTask, ApprovalRequest, KnowledgeDocument, Lead, ToolRecord, User
from app.schemas import AgentCreate, AgentOut, AgentUpdate, DashboardOut, ToolOut
from app.tools.base import tool_registry
from app.utils import utcnow

router = APIRouter(tags=["agents"])


def _validate_tools(names: list[str]) -> None:
    unknown = sorted(set(names) - set(tool_registry.names()))
    if unknown:
        raise HTTPException(status_code=422, detail=f"ابزار ناشناخته: {', '.join(unknown)}")


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DashboardOut:
    agents = sum(
        1
        for row in db.scalars(select(Agent).where(Agent.is_active.is_(True))).all()
        if agent_allowed(user, row.slug)
    )
    approvals = db.scalars(select(ApprovalRequest).where(ApprovalRequest.status == "pending")).all()
    from app.auth.rbac import can_decide_approval

    pending = sum(1 for row in approvals if can_decide_approval(db, user, row))
    lead_stmt = select(Lead)
    party = party_for_role(user.role)
    if party:
        lead_stmt = lead_stmt.where(Lead.party == party)
    leads = len(db.scalars(lead_stmt).all())
    documents = db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
    task_stmt = select(AgentTask).where(
        AgentTask.status.in_(("queued", "running", "waiting_approval"))
    )
    running = 0
    from app.auth.rbac import task_visible

    for task in db.scalars(task_stmt).all():
        if task_visible(db, user, task):
            running += 1
    return DashboardOut(
        agents=int(agents),
        pending_approvals=int(pending),
        leads=int(leads),
        documents=int(documents),
        running_tasks=int(running),
        mock_llm=settings.llm_is_mock(),
        max_discount_percent=settings.max_discount_percent,
    )


@router.get("/tools", response_model=list[ToolOut])
def list_tools(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ToolOut]:
    rows = {row.name: row for row in db.scalars(select(ToolRecord)).all()}
    items: list[ToolOut] = []
    for tool in tool_registry.list():
        row = rows.get(tool.name)
        items.append(
            ToolOut(
                name=tool.name,
                description=tool.description,
                kind=tool.kind,
                provider=tool.provider,
                is_enabled=True if row is None else row.is_enabled,
                input_schema=tool.input_schema,
            )
        )
    return items


@router.get("/agents", response_model=list[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Agent]:
    rows = list(db.scalars(select(Agent).order_by(Agent.name_fa)))
    return [row for row in rows if agent_allowed(user, row.slug)]


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None or not agent_allowed(user, agent.slug):
        raise HTTPException(status_code=404, detail="عامل پیدا نشد")
    return agent


@router.post("/agents", response_model=AgentOut, status_code=201)
def create_agent(
    body: AgentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
) -> Agent:
    if not SLUG_RE.match(body.slug):
        raise HTTPException(
            status_code=422,
            detail="شناسه باید با حرف کوچک انگلیسی شروع شود و فقط شامل حرف، عدد و _ باشد",
        )
    _validate_tools(body.allowed_tools)
    if db.scalar(select(Agent).where(Agent.slug == body.slug)):
        raise HTTPException(status_code=409, detail="این شناسه قبلاً ثبت شده است")
    agent = Agent(
        slug=body.slug,
        name=body.name.strip(),
        name_fa=body.name_fa.strip(),
        description=body.description.strip(),
        system_prompt=body.system_prompt.strip(),
        allowed_tools=body.allowed_tools,
        model_strong=body.model_strong.strip(),
        model_fast=body.model_fast.strip(),
        model_strong_is_default=False,
        model_fast_is_default=False,
        temperature=body.temperature,
        is_active=body.is_active,
        source="panel",
        config={},
    )
    db.add(agent)
    db.flush()
    write_audit(
        db,
        actor_id=actor.id,
        action="agent.create",
        entity_type="agent",
        entity_id=agent.id,
        details={"slug": agent.slug},
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="عامل پیدا نشد")
    data = body.model_dump(exclude_unset=True)
    if "allowed_tools" in data and data["allowed_tools"] is not None:
        _validate_tools(data["allowed_tools"])
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(agent, field, value)
    if "model_strong" in data:
        agent.model_strong_is_default = False
    if "model_fast" in data:
        agent.model_fast_is_default = False
    agent.updated_at = utcnow()
    write_audit(
        db,
        actor_id=actor.id,
        action="agent.update",
        entity_type="agent",
        entity_id=agent.id,
        details={"fields": sorted(data)},
    )
    db.commit()
    db.refresh(agent)
    return agent
