"""Delegate specialist work as linked child tasks."""

from __future__ import annotations

from langgraph.errors import GraphInterrupt
from sqlalchemy import func, select

from app.auth.rbac import SPECIALISTS, agent_allowed
from app.config import settings
from app.models import Agent, AgentTask, User
from app.runtime.context import RunContext
from app.runtime.delegate import run_delegated
from app.runtime.events import emit_event
from app.utils import new_id, utcnow


async def delegate_jobs(context: RunContext, jobs: list[dict]) -> str:
    if context.depth >= settings.supervisor_max_depth:
        return "سقف عمق سرپرست پر شده است و سپردن دوباره مجاز نیست."
    cleaned = []
    for job in jobs:
        slug = str(job.get("agent_slug") or "").strip()
        goal = str(job.get("goal") or "").strip()
        if slug and goal:
            cleaned.append({"agent_slug": slug, "goal": goal})
    if not cleaned:
        return "زیروظیفه‌ای برای سپردن نیست."
    if len(cleaned) > settings.supervisor_max_children:
        return f"بیش از {settings.supervisor_max_children} زیروظیفه در یک گام مجاز نیست."
    user = context.db.get(User, context.user_id) if context.user_id else None
    for job in cleaned:
        if job["agent_slug"] not in SPECIALISTS:
            return f"عامل {job['agent_slug']} متخصص قابل سپردن نیست."
        if user is not None and not agent_allowed(user, job["agent_slug"]):
            return f"نقش شما نمی‌تواند کار را به {job['agent_slug']} بسپارد."
    existing = context.db.scalar(
        select(func.count())
        .select_from(AgentTask)
        .where(AgentTask.parent_task_id == context.task_id)
    )
    if int(existing or 0) + len(cleaned) > settings.supervisor_max_children:
        return "بودجهٔ تعداد فرزندان این وظیفه تمام شده است."
    # One database session is shared with the parent graph, so children run
    # one after another. Independent jobs still arrive in a single delegate call.
    reports = []
    for job in cleaned:
        reports.append(await _one(context, job))
    merged = "\n\n".join(part for part in reports if part)
    return merged or "متخصص‌ها گزارشی برنگرداندند."


async def _one(context: RunContext, job: dict) -> str:
    slug = job["agent_slug"]
    goal = job["goal"]
    agent = (
        context.db.query(Agent).filter(Agent.slug == slug, Agent.is_active.is_(True)).one_or_none()
    )
    if agent is None:
        return f"عامل فعالی با شناسه {slug} پیدا نشد."
    child = AgentTask(
        id=new_id(),
        user_id=context.user_id,
        agent_id=agent.id,
        goal=goal,
        status="running",
        thread_id=new_id(),
        parent_task_id=context.task_id,
        depth=context.depth + 1,
        max_steps=max(2, min(6, int(context.budget or 6))),
    )
    context.db.add(child)
    context.db.commit()
    emit_event(
        context.db,
        context.task_id,
        "delegate.start",
        {"child_id": child.id, "agent_slug": slug, "goal": goal[:500]},
    )
    emit_event(
        context.db,
        context.task_id,
        "child.task",
        {"child_id": child.id, "status": "running", "agent_slug": slug},
    )
    try:
        report = await run_delegated(agent_slug=slug, goal=goal, context=context)
        child.status = "completed"
        child.report = report
        child.finished_at = utcnow()
        context.db.commit()
        emit_event(
            context.db,
            context.task_id,
            "delegate.end",
            {"child_id": child.id, "agent_slug": slug, "preview": report[:400]},
        )
        return f"## {agent.name_fa}\n{report}"
    except GraphInterrupt:
        child.status = "waiting_approval"
        context.db.commit()
        emit_event(
            context.db,
            context.task_id,
            "child.task",
            {"child_id": child.id, "status": "waiting_approval", "agent_slug": slug},
        )
        raise
    except Exception as exc:
        child.status = "failed"
        child.error = str(exc)[:1000]
        child.finished_at = utcnow()
        context.db.commit()
        return f"## {agent.name_fa}\nاجرای زیروظیفه ناموفق بود: {exc}"
