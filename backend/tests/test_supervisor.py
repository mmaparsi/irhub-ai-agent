"""Supervisor delegation uses a scripted model and records child tasks."""

import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from app.config import settings
from app.models import Agent, AgentTask, User
from app.runtime.context import RunContext, run_context
from app.runtime.llm import scripted_llm
from app.runtime.supervisor import delegate_jobs
from app.utils import new_id


def _parent(db, user: User) -> tuple[AgentTask, RunContext]:
    agent = db.query(Agent).filter(Agent.slug == "supervisor").one()
    task = AgentTask(
        user_id=user.id,
        agent_id=agent.id,
        goal="جمع‌بندی بازار",
        status="running",
        thread_id=new_id(),
        max_steps=6,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    ctx = RunContext(
        db=db,
        task_id=task.id,
        user_id=user.id,
        agent_id=agent.id,
        agent_slug="supervisor",
        thread_id=task.thread_id,
        saver=InMemorySaver(),
        depth=0,
        budget=6,
    )
    return task, ctx


def test_delegate_writes_child_report(client):
    from app.database import open_session

    db = open_session()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").one()
        task, ctx = _parent(db, admin)

        async def run() -> str:
            script = scripted_llm.set(
                [
                    {"content": "برنامه: فقط جمع‌بندی کن.", "tool_calls": []},
                    {"content": "یافته: بازار آرام است.", "tool_calls": []},
                    {"content": "گزارش فرزند: بازار آرام است.", "tool_calls": []},
                ]
            )
            token = run_context.set(ctx)
            try:
                return await delegate_jobs(
                    ctx, [{"agent_slug": "consulting", "goal": "خلاصه بازار فولاد"}]
                )
            finally:
                run_context.reset(token)
                scripted_llm.reset(script)

        text = asyncio.run(run())
        assert "بازار آرام" in text
        child = db.query(AgentTask).filter(AgentTask.parent_task_id == task.id).one()
        assert child.status == "completed"
        assert child.depth == 1
    finally:
        db.close()


def test_sales_cannot_delegate_outside_role(client):
    from app.database import open_session

    db = open_session()
    try:
        sales = db.query(User).filter(User.email == "sales@example.com").one()
        _task, ctx = _parent(db, sales)

        async def run() -> str:
            token = run_context.set(ctx)
            try:
                return await delegate_jobs(
                    ctx, [{"agent_slug": "research", "goal": "بررسی تأمین‌کننده"}]
                )
            finally:
                run_context.reset(token)

        text = asyncio.run(run())
        assert "نمی‌تواند" in text
        assert db.query(AgentTask).filter(AgentTask.parent_task_id == ctx.task_id).count() == 0
    finally:
        db.close()


def test_depth_guard(client):
    from app.database import open_session

    db = open_session()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").one()
        _task, ctx = _parent(db, admin)
        ctx.depth = settings.supervisor_max_depth

        async def run() -> str:
            token = run_context.set(ctx)
            try:
                return await delegate_jobs(ctx, [{"agent_slug": "consulting", "goal": "دوباره"}])
            finally:
                run_context.reset(token)

        text = asyncio.run(run())
        assert "سقف عمق" in text
    finally:
        db.close()
