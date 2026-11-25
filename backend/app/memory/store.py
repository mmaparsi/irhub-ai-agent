"""Long-term memories. Vector search when embeddings exist, otherwise Postgres FTS."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.rbac import ADMIN, SALES, SUPPLIER, agent_allowed
from app.knowledge.embeddings import try_embed
from app.models import Memory, User
from app.runtime.events import emit_event
from app.utils import utcnow

ENTITY_TYPES = frozenset({"lead", "customer", "supplier", "general"})


def remember(
    db: Session,
    *,
    content: str,
    user_id: str | None,
    agent_type: str = "",
    entity_type: str = "general",
    entity_id: str | None = None,
    importance: int = 1,
    task_id: str | None = None,
) -> Memory:
    body = (content or "").strip()
    kind = entity_type if entity_type in ENTITY_TYPES else "general"
    row = Memory(
        user_id=user_id,
        agent_type=agent_type or "",
        entity_type=kind,
        entity_id=entity_id or None,
        content=body[:8000],
        embedding=try_embed(body),
        importance=max(1, min(int(importance or 1), 5)),
        last_accessed_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if task_id:
        emit_event(
            db,
            task_id,
            "memory.saved",
            {"id": row.id, "entity_type": row.entity_type, "preview": body[:240]},
        )
    return row


def recall(
    db: Session,
    *,
    query: str,
    user: User | None = None,
    user_id: str | None = None,
    agent_type: str = "",
    entity_type: str | None = None,
    entity_id: str | None = None,
    k: int = 5,
    task_id: str | None = None,
) -> list[Memory]:
    limit = max(1, min(int(k or 5), 12))
    stmt = select(Memory)
    if user is not None and user.role != ADMIN:
        stmt = stmt.where(_role_filter(user))
    elif user_id:
        stmt = stmt.where(or_(Memory.user_id == user_id, Memory.user_id.is_(None)))
    if entity_type:
        stmt = stmt.where(Memory.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Memory.entity_id == entity_id)
    if agent_type and (user is None or user.role == ADMIN):
        stmt = stmt.where(Memory.agent_type == agent_type)
    rows = _search(db, stmt, query, limit)
    now = utcnow()
    for row in rows:
        row.last_accessed_at = now
    if rows:
        db.commit()
    if task_id and rows:
        emit_event(
            db,
            task_id,
            "memory.recalled",
            {"query": query[:200], "count": len(rows), "ids": [row.id for row in rows]},
        )
    return rows


def recall_block(
    db: Session, user_id: str | None, agent_type: str, query: str, task_id: str
) -> str:
    rows = recall(
        db,
        query=query,
        user_id=user_id,
        agent_type=agent_type,
        k=4,
        task_id=task_id,
    )
    if not rows:
        return ""
    lines = [f"- ({row.entity_type}) {row.content[:400]}" for row in rows]
    return "حافظهٔ مرتبط:\n" + "\n".join(lines)


def visible(user: User, row: Memory) -> bool:
    if user.role == ADMIN:
        return True
    if row.agent_type and not agent_allowed(user, row.agent_type):
        return False
    if user.role == SALES and row.entity_type == "supplier":
        return False
    if user.role == SUPPLIER and row.entity_type == "customer":
        return False
    return True


def _role_filter(user: User):
    if user.role == SALES:
        return Memory.agent_type.in_(["lead_generation", "sales_negotiation", "supervisor", ""])
    if user.role == SUPPLIER:
        return Memory.agent_type.in_(["research", "consulting", "supervisor", ""])
    return Memory.user_id == user.id


def _search(db: Session, stmt, query: str, limit: int) -> list[Memory]:
    vector = try_embed(query)
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if vector is not None and dialect == "postgresql":
        distance = Memory.embedding.cosine_distance(vector)
        ranked = stmt.where(Memory.embedding.is_not(None)).order_by(distance).limit(limit)
        found = list(db.scalars(ranked).all())
        if found:
            return found
    if dialect == "postgresql":
        try:
            match = func.to_tsvector("simple", Memory.content).op("@@")(
                func.plainto_tsquery("simple", query)
            )
            found = list(db.scalars(stmt.where(match).limit(limit)).all())
            if found:
                return found
        except Exception:
            db.rollback()
    like = f"%{query.strip()}%"
    if not query.strip():
        return list(db.scalars(stmt.order_by(Memory.created_at.desc()).limit(limit)).all())
    return list(
        db.scalars(
            stmt.where(Memory.content.ilike(like)).order_by(Memory.importance.desc()).limit(limit)
        ).all()
    )


def delete_memory(db: Session, row: Memory) -> None:
    db.delete(row)
    db.commit()


def negotiation_note(
    db: Session,
    *,
    user_id: str | None,
    lead_id: str,
    content: str,
    agent_type: str,
    task_id: str | None,
) -> Memory:
    return remember(
        db,
        content=content,
        user_id=user_id,
        agent_type=agent_type,
        entity_type="lead",
        entity_id=lead_id,
        importance=3,
        task_id=task_id,
    )
