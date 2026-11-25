from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ActivityEvent, AgentTask, TaskEvent, User
from app.realtime import hub

_LOUD = {"status", "approval", "error", "report", "lead"}


def emit_event(
    db: Session,
    task_id: str,
    kind: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
) -> TaskEvent | None:
    if dedupe_key:
        existing = db.scalar(
            select(TaskEvent).where(
                TaskEvent.task_id == task_id, TaskEvent.dedupe_key == dedupe_key
            )
        )
        if existing is not None:
            return existing
    current = db.scalar(select(func.max(TaskEvent.seq)).where(TaskEvent.task_id == task_id))
    row = TaskEvent(
        task_id=task_id,
        seq=int(current or 0) + 1,
        kind=kind,
        payload=payload,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    hub.publish(
        {
            "type": "task",
            "task_id": task_id,
            "seq": row.seq,
            "kind": kind,
            "payload": payload,
            "id": row.id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    )
    if kind in _LOUD:
        task = db.get(AgentTask, task_id)
        user = db.get(User, task.user_id) if task is not None else None
        publish_activity(
            db,
            kind=kind,
            payload={"task_id": task_id, **payload},
            user_id=task.user_id if task is not None else None,
            role=user.role if user is not None else "",
            task_id=task_id,
        )
    return row


def publish_activity(
    db: Session,
    *,
    kind: str,
    payload: dict[str, Any],
    user_id: str | None = None,
    role: str = "",
    task_id: str | None = None,
) -> ActivityEvent:
    current = db.scalar(select(func.max(ActivityEvent.seq)))
    row = ActivityEvent(
        seq=int(current or 0) + 1,
        kind=kind,
        payload=payload,
        user_id=user_id,
        role=role or "",
        task_id=task_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    hub.publish(
        {
            "type": "activity",
            "seq": row.seq,
            "kind": kind,
            "payload": payload,
            "user_id": user_id,
            "role": role or "",
            "task_id": task_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    )
    return row


def note_progress(context: object, message: str, **payload: Any) -> None:
    db = getattr(context, "db", None)
    task_id = getattr(context, "task_id", None)
    if db is None or not task_id:
        return
    emit_event(db, task_id, "tool_progress", {"message": message, **payload})
