from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import TaskEvent


def emit_event(
    db: Session,
    task_id: str,
    kind: str,
    payload: dict[str, Any],
    *,
    dedupe_key: str | None = None,
) -> None:
    if dedupe_key:
        existing = db.scalar(
            select(TaskEvent).where(
                TaskEvent.task_id == task_id, TaskEvent.dedupe_key == dedupe_key
            )
        )
        if existing is not None:
            return
    current = db.scalar(select(func.max(TaskEvent.seq)).where(TaskEvent.task_id == task_id))
    db.add(
        TaskEvent(
            task_id=task_id,
            seq=int(current or 0) + 1,
            kind=kind,
            payload=payload,
            dedupe_key=dedupe_key,
        )
    )
    db.commit()
