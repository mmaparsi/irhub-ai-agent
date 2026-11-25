"""List, search, and delete long-term memories."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_staff
from app.database import get_db
from app.memory.store import delete_memory, recall, visible
from app.models import Memory, User

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryOut(BaseModel):
    id: str
    agent_type: str
    entity_type: str
    entity_id: str | None
    content: str
    importance: int
    created_at: str
    last_accessed_at: str


def _out(row: Memory) -> MemoryOut:
    return MemoryOut(
        id=row.id,
        agent_type=row.agent_type,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        content=row.content,
        importance=row.importance,
        created_at=row.created_at.isoformat(),
        last_accessed_at=row.last_accessed_at.isoformat(),
    )


@router.get("", response_model=list[MemoryOut])
def list_memories(
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> list[MemoryOut]:
    if q.strip():
        rows = recall(db, query=q.strip(), user=user, k=30)
    else:
        rows = list(db.scalars(select(Memory).order_by(Memory.created_at.desc()).limit(80)).all())
        rows = [row for row in rows if visible(user, row)]
    return [_out(row) for row in rows]


@router.delete("/{memory_id}", status_code=204)
def remove_memory(
    memory_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> None:
    row = db.get(Memory, memory_id)
    if row is None or not visible(user, row):
        raise HTTPException(status_code=404, detail="حافظه پیدا نشد")
    delete_memory(db, row)
