from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_staff
from app.auth.rbac import require_agent, task_visible
from app.config import settings
from app.database import get_db
from app.models import Agent, AgentTask, Artifact, TaskEvent, User
from app.runtime.executor import execute_task
from app.schemas import AgentTaskIn, AgentTaskOut
from app.utils import utcnow
from app.worker.queue import enqueue

router = APIRouter(prefix="/agent-tasks", tags=["tasks"])

TERMINAL = {"completed", "failed", "stopped"}


def _out(db: Session, task: AgentTask) -> AgentTaskOut:
    agent = db.get(Agent, task.agent_id) if task.agent_id else None
    return AgentTaskOut(
        id=task.id,
        goal=task.goal,
        status=task.status,
        plan=task.plan or "",
        report=task.report or "",
        step=task.step,
        max_steps=task.max_steps,
        error=task.error or "",
        agent_id=task.agent_id,
        agent_name=agent.name_fa if agent else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
        finished_at=task.finished_at,
    )


def spawn_task(task_id: str, resume: dict | None = None) -> None:
    def _run() -> None:
        asyncio.run(execute_task(task_id, resume))

    threading.Thread(target=_run, name=f"task-{task_id[:8]}", daemon=True).start()


async def enqueue_or_spawn(task_id: str, resume: dict | None = None) -> None:
    # Tests share one SQLite database. A daemon thread races with the next test
    # and locks or drops that database. Run inline only in the test environment.
    if settings.environment == "test":
        await execute_task(task_id, resume)
        return
    if resume is None:
        queued = await enqueue("run_agent_task", task_id)
    else:
        import json

        queued = await enqueue("resume_agent_task", task_id, json.dumps(resume, ensure_ascii=False))
    if not queued:
        spawn_task(task_id, resume)


@router.get("", response_model=list[AgentTaskOut])
def list_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> list[AgentTaskOut]:
    stmt = select(AgentTask).order_by(AgentTask.created_at.desc()).limit(80)
    rows = [row for row in db.scalars(stmt).all() if task_visible(db, user, row)]
    return [_out(db, row) for row in rows]


@router.post("", response_model=AgentTaskOut, status_code=201)
async def create_task(
    body: AgentTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> AgentTaskOut:
    agent = None
    if body.agent_id:
        agent = db.get(Agent, body.agent_id)
    elif body.agent_slug:
        agent = db.scalar(
            select(Agent).where(Agent.slug == body.agent_slug, Agent.is_active.is_(True))
        )
    agent = require_agent(user, agent)
    task = AgentTask(
        user_id=user.id,
        agent_id=agent.id,
        goal=body.goal.strip(),
        status="queued",
        thread_id="",
        max_steps=body.max_steps,
    )
    db.add(task)
    db.flush()
    task.thread_id = task.id
    db.commit()
    db.refresh(task)
    await enqueue_or_spawn(task.id)
    return _out(db, task)


@router.get("/{task_id}", response_model=AgentTaskOut)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> AgentTaskOut:
    task = _visible(db, user, task_id)
    return _out(db, task)


@router.get("/{task_id}/events")
def list_events(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    _visible(db, user, task_id)
    rows = db.scalars(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.seq)
    ).all()
    return [
        {
            "id": row.id,
            "seq": row.seq,
            "kind": row.kind,
            "payload": row.payload,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/{task_id}/stream")
async def stream_events(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    _visible(db, user, task_id)

    async def generate():
        import json

        from app.database import open_session

        seen = 0
        while True:
            session = open_session()
            try:
                rows = session.scalars(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == task_id, TaskEvent.seq > seen)
                    .order_by(TaskEvent.seq)
                ).all()
                payloads = [
                    {"seq": row.seq, "kind": row.kind, "payload": row.payload} for row in rows
                ]
                task = session.get(AgentTask, task_id)
                status = task.status if task else "failed"
                if rows:
                    seen = rows[-1].seq
            finally:
                session.close()
            for payload in payloads:
                yield f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            if status in TERMINAL and not payloads:
                yield f"data: {json.dumps({'kind': 'status', 'payload': {'status': status}})}\n\n"
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{task_id}/stop", response_model=AgentTaskOut)
def stop_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> AgentTaskOut:
    task = _visible(db, user, task_id)
    if task.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="دسترسی مجاز نیست")
    if task.status in TERMINAL:
        return _out(db, task)
    task.status = "stopped" if task.status == "waiting_approval" else "stopping"
    if task.status == "stopped":
        task.finished_at = utcnow()
        task.report = task.report or "اجرای وظیفه توسط کاربر متوقف شد."
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return _out(db, task)


@router.get("/{task_id}/artifacts")
def list_artifacts(
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    _visible(db, user, task_id)
    rows = db.scalars(select(Artifact).where(Artifact.task_id == task_id)).all()
    return [
        {"id": row.id, "filename": row.filename, "media_type": row.media_type, "size": row.size}
        for row in rows
    ]


def _visible(db: Session, user: User, task_id: str) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None or not task_visible(db, user, task):
        raise HTTPException(status_code=404, detail="وظیفه پیدا نشد")
    return task


artifacts = APIRouter(prefix="/artifacts", tags=["artifacts"])


@artifacts.get("/{artifact_id}")
def download_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    row = db.get(Artifact, artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")
    if row.task_id:
        _visible(db, user, row.task_id)
    return FileResponse(row.path, filename=row.filename, media_type=row.media_type)
