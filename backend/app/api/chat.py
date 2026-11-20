from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import get_compiled_graph, next_seq
from app.agents.runner import iter_turn
from app.agents.supervisor import route_task
from app.auth.deps import require_staff
from app.auth.rbac import agent_allowed, require_agent, team_user_ids
from app.database import get_db, open_session
from app.models import Agent, Conversation, Message, User
from app.schemas import (
    ConversationDetail,
    ConversationIn,
    ConversationOut,
    MessageIn,
    MessageOut,
    TaskIn,
    TaskOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


def _agent_name(db: Session, agent_id: str | None) -> str | None:
    if not agent_id:
        return None
    agent = db.get(Agent, agent_id)
    return agent.name_fa if agent else None


def _conversation_out(db: Session, conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status,
        agent_id=conversation.agent_id,
        agent_name=_agent_name(db, conversation.agent_id),
        channel=conversation.channel or "panel",
        party=conversation.party or "customer",
        created_at=conversation.created_at,
    )


def _owns(db: Session, user: User, conversation: Conversation) -> bool:
    if user.role == "admin":
        return True
    owner = db.get(User, conversation.user_id)
    return owner is not None and owner.role == user.role


def _visible(db: Session, user: User):
    stmt = select(Conversation).order_by(Conversation.created_at.desc())
    if user.role != "admin":
        stmt = stmt.where(Conversation.user_id.in_(team_user_ids(db, user)))
    return stmt


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> list[ConversationOut]:
    rows = db.scalars(_visible(db, user).limit(80)).all()
    return [_conversation_out(db, row) for row in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: ConversationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> ConversationOut:
    agent_id = body.agent_id
    if agent_id:
        require_agent(user, db.get(Agent, agent_id))
    conversation = Conversation(
        user_id=user.id,
        agent_id=agent_id,
        title=(body.title or "").strip() or "گفتگوی جدید",
        status="open",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_out(db, conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> ConversationDetail:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or not _owns(db, user, conversation):
        raise HTTPException(status_code=404, detail="گفتگو پیدا نشد")
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.seq)
    ).all()
    base = _conversation_out(db, conversation)
    return ConversationDetail(
        **base.model_dump(),
        messages=[
            MessageOut(
                id=item.id,
                role=item.role,
                content=item.content,
                seq=item.seq,
                created_at=item.created_at,
            )
            for item in messages
        ],
    )


def _resolve_agent(db: Session, conversation: Conversation, text: str) -> Agent | None:
    if conversation.agent_id:
        agent = db.get(Agent, conversation.agent_id)
        if agent is not None and agent.is_active:
            return agent
        return None
    slug = route_task(text, None)
    return db.scalar(select(Agent).where(Agent.slug == slug, Agent.is_active.is_(True)))


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: str,
    body: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> StreamingResponse:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or not _owns(db, user, conversation):
        raise HTTPException(status_code=404, detail="گفتگو پیدا نشد")
    conv_id = conversation.id
    user_id = user.id
    content = body.content.strip()
    tier = body.tier

    async def generate():
        # Routing uses the same function as the LangGraph supervisor node.
        # Tokens are streamed from the specialist runner; POST /tasks runs the
        # compiled graph and returns the finished text.
        session = open_session()
        try:
            current = session.get(Conversation, conv_id)
            if current is None:
                yield _sse({"error": "گفتگو پیدا نشد"})
                return
            agent = _resolve_agent(session, current, content)
            if agent is None or not agent_allowed(user, agent.slug):
                yield _sse({"error": "عامل فعالی برای نقش شما پیدا نشد"})
                return
            if current.agent_id is None:
                current.agent_id = agent.id
            history_rows = session.scalars(
                select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq)
            ).all()
            history = [
                {"role": item.role, "content": item.content}
                for item in history_rows
                if item.role in {"user", "assistant"}
            ]
            session.add(
                Message(
                    conversation_id=conv_id,
                    seq=next_seq(session, conv_id),
                    role="user",
                    content=content,
                )
            )
            session.commit()
            parts: list[str] = []
            approvals: list[str] = []
            async for kind, payload in iter_turn(
                session,
                agent=agent,
                history=history,
                user_text=content,
                tier=tier,
                user_id=user_id,
                conversation_id=conv_id,
            ):
                if kind == "token":
                    parts.append(str(payload))
                    yield _sse({"token": payload})
                elif kind == "approval" and payload:
                    approvals.append(str(payload))
            session.add(
                Message(
                    conversation_id=conv_id,
                    seq=next_seq(session, conv_id),
                    role="assistant",
                    content="".join(parts),
                )
            )
            session.commit()
            yield _sse({"done": True, "approval_ids": approvals, "agent_slug": agent.slug})
        except Exception:
            session.rollback()
            logger.exception("chat stream failed")
            yield _sse({"error": "خطا در تولید پاسخ"})
        finally:
            session.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/tasks", response_model=TaskOut)
async def run_task(
    body: TaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> TaskOut:
    slug = route_task(body.task, body.agent_slug)
    agent = db.scalar(select(Agent).where(Agent.slug == slug, Agent.is_active.is_(True)))
    if agent is None or not agent_allowed(user, agent.slug):
        raise HTTPException(status_code=403, detail="این عامل برای نقش شما در دسترس نیست")
    conversation = Conversation(
        user_id=user.id,
        agent_id=agent.id,
        title=body.task.strip()[:80] or "کار",
        status="open",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    result = await get_compiled_graph().ainvoke(
        {
            "task": body.task.strip(),
            "agent_slug": slug,
            "user_id": user.id,
            "conversation_id": conversation.id,
            "tier": body.tier,
            "history": [],
        }
    )
    return TaskOut(
        conversation_id=conversation.id,
        agent_slug=result.get("agent_slug") or slug,
        result=result.get("result") or "",
        approval_ids=list(result.get("approval_ids") or []),
    )
