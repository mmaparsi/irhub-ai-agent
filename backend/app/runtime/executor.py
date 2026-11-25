"""Run or resume an autonomous task. Postgres checkpoints survive process restarts."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.config import settings
from app.database import open_session
from app.models import Agent, AgentTask
from app.runtime.context import RunContext, run_context
from app.runtime.events import emit_event
from app.runtime.graph import build_agent_graph
from app.utils import utcnow

logger = logging.getLogger(__name__)

_memory = InMemorySaver()


def postgres_dsn() -> str:
    return settings.database_url.replace("postgresql+psycopg", "postgresql", 1)


@asynccontextmanager
async def open_checkpointer(dialect: str):
    if dialect == "postgresql":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(postgres_dsn()) as saver:
            await saver.setup()
            yield saver
    else:
        yield _memory


async def execute_task(task_id: str, resume: dict | None = None) -> None:
    db = open_session()
    try:
        task = db.get(AgentTask, task_id)
        if task is None:
            return
        if resume is None and task.status in {"completed", "failed", "stopped"}:
            return
        agent = db.get(Agent, task.agent_id) if task.agent_id else None
        if agent is None:
            task.status = "failed"
            task.error = "عامل وظیفه پیدا نشد."
            db.commit()
            return
        dialect = db.bind.dialect.name if db.bind is not None else ""
        task.status = "running"
        task.error = ""
        task.updated_at = utcnow()
        emit_event(
            db,
            task.id,
            "status",
            {"status": "running"},
            dedupe_key=f"{task.id}:status:running",
        )
        async with open_checkpointer(dialect) as saver:
            graph = build_agent_graph(saver)
            config = {
                "configurable": {"thread_id": task.thread_id},
                "recursion_limit": int(task.max_steps) * 4 + 8,
            }
            ctx = RunContext(
                db=db,
                task_id=task.id,
                user_id=task.user_id,
                agent_id=agent.id,
                agent_slug=agent.slug,
                thread_id=task.thread_id,
                saver=saver,
                depth=int(task.depth or 0),
                budget=int(task.max_steps or 6),
            )
            token = run_context.set(ctx)
            try:
                from langgraph.errors import GraphInterrupt

                snapshot = await graph.aget_state(config)
                try:
                    if resume is not None:
                        await graph.ainvoke(Command(resume=resume), config)
                    elif snapshot.values and snapshot.next:
                        await graph.ainvoke(None, config)
                    elif not snapshot.values:
                        await graph.ainvoke(_initial(task, agent), config)
                except GraphInterrupt:
                    logger.info("task %s interrupted for approval", task_id)
                snapshot = await graph.aget_state(config)
            finally:
                run_context.reset(token)
        task = db.get(AgentTask, task_id)
        if task is None:
            return
        values = snapshot.values or {}
        task.plan = values.get("plan") or task.plan
        task.report = values.get("report") or task.report
        task.step = int(values.get("step") or task.step or 0)
        task.updated_at = utcnow()
        if snapshot.interrupts:
            task.status = "waiting_approval"
            emit_event(
                db,
                task.id,
                "approval",
                {"interrupt": _jsonable(snapshot.interrupts[0].value)},
                dedupe_key=f"approval:{_jsonable(snapshot.interrupts[0].value).get('approval_id')}",
            )
        elif values.get("status") == "stopped" or task.status == "stopping":
            task.status = "stopped"
            task.finished_at = utcnow()
            task.report = values.get("report") or "اجرای وظیفه توسط کاربر متوقف شد."
        else:
            task.status = "completed"
            task.finished_at = utcnow()
            await _remember_outcome(db, task, agent)
        emit_event(
            db,
            task.id,
            "status",
            {"status": task.status},
            dedupe_key=f"{task.id}:status:{task.status}",
        )
    except Exception as exc:
        logger.exception("task %s failed", task_id)
        db.rollback()
        task = db.get(AgentTask, task_id)
        if task is not None and task.status not in {"completed", "stopped"}:
            task.status = "failed"
            task.error = str(exc)[:2000]
            task.updated_at = utcnow()
            task.finished_at = utcnow()
            emit_event(db, task.id, "error", {"message": task.error})
            db.commit()
    finally:
        db.close()


def _initial(task: AgentTask, agent: Agent) -> dict:
    return {
        "goal": task.goal,
        "plan": "",
        "report": "",
        "messages": [],
        "step": 0,
        "max_steps": task.max_steps,
        "status": "running",
        "model": agent.model_strong,
        "fast_model": agent.model_fast,
        "temperature": agent.temperature,
        "allowed_tools": list(agent.allowed_tools or []),
        "system_prompt": agent.system_prompt,
        "agent_name": agent.name_fa,
    }


async def _remember_outcome(db, task: AgentTask, agent: Agent | None) -> None:
    """Store a durable fact. Mock and scripted runs skip the model so tests stay deterministic."""
    from app.memory.store import remember
    from app.runtime.llm import complete, scripted_llm

    report = (task.report or "").strip()
    if not report or agent is None:
        return
    if scripted_llm.get() is not None or settings.llm_is_mock():
        return
    text = report[:700]
    try:
        summarized = await complete(
            phase="memory",
            messages=[
                {
                    "role": "system",
                    "content": "یک واقعیت کوتاه و ماندگار از این گزارش استخراج کن. اگر چیز ماندگاری نیست فقط «-» بنویس.",
                },
                {"role": "user", "content": text},
            ],
            tools=None,
            model=agent.model_fast,
            fast_model=agent.model_fast,
            temperature=0.1,
        )
        text = (summarized.get("content") or "").strip() or text
    except Exception:
        logger.warning("task memory summary skipped", exc_info=True)
    if not text or text == "-":
        return
    remember(
        db,
        content=text,
        user_id=task.user_id,
        agent_type=agent.slug,
        entity_type="general",
        importance=2,
        task_id=task.id,
    )


def _jsonable(value):
    if isinstance(value, dict):
        return value
    return {"value": str(value)}
