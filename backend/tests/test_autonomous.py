from __future__ import annotations

import time

from sqlalchemy import select

from app.models import Agent, AgentTask, ApprovalRequest, Company, Lead, TaskEvent
from app.runtime.executor import execute_task
from app.runtime.llm import scripted_llm
from app.tools.search import _searxng
from tests.conftest import auth_header


def test_searxng_parser(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "results": [
                    {"title": "مبل سازان", "url": "https://example.com/a", "content": "تهران"}
                ]
            }

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, params):
            assert params["format"] == "json"
            assert "مبل" in params["q"]
            return Response()

    monkeypatch.setattr("app.tools.search.httpx.Client", lambda **kwargs: Client())
    monkeypatch.setattr("app.tools.search.settings.searxng_url", "http://searxng:8080")
    monkeypatch.setattr("app.tools.search.settings.tavily_api_key", "")
    monkeypatch.setattr("app.tools.search.settings.brave_api_key", "")
    rows = _searxng("مبل تهران", 5)
    assert rows[0]["title"] == "مبل سازان"
    assert rows[0]["url"] == "https://example.com/a"


def test_graph_creates_a_lead_and_reports(client) -> None:
    headers = auth_header(client)
    agents = client.get("/api/agents", headers=headers).json()
    agent = next(item for item in agents if item["slug"] == "lead_generation")
    created = client.post(
        "/api/agent-tasks",
        headers=headers,
        json={
            "agent_id": agent["id"],
            "goal": "یک تولیدکننده مبل در تهران را به عنوان سرنخ ثبت کن",
            "max_steps": 4,
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    _wait_until_done(task_id)
    from app.database import open_session

    db = open_session()
    try:
        task = db.get(AgentTask, task_id)
        assert task is not None
        assert task.status == "completed", task.error
        assert "گزارش" in (task.report or "")
        events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id)).all()
        kinds = {item.kind for item in events}
        assert "plan" in kinds
        assert "tool_result" in kinds
        company = db.scalar(select(Company).where(Company.name == "تولیدی نمونه تهران"))
        assert company is not None
        lead = db.scalar(select(Lead).where(Lead.company_id == company.id))
        assert lead is not None
    finally:
        db.close()


def test_email_tool_pauses_and_resumes(client) -> None:
    headers = auth_header(client)
    from app.database import open_session

    db = open_session()
    try:
        agent = db.scalar(select(Agent).where(Agent.slug == "sales_negotiation"))
        assert agent is not None
        task = AgentTask(
            user_id=_user_id(db),
            agent_id=agent.id,
            goal="برای مشتری ایمیل پیش‌نویس کن",
            status="queued",
            thread_id="",
            max_steps=4,
        )
        db.add(task)
        db.flush()
        task.thread_id = task.id
        db.commit()
        task_id = task.id
    finally:
        db.close()
    token = scripted_llm.set(
        [
            {"content": "برنامه: یک ایمیل بنویس و منتظر تأیید بمان.", "tool_calls": []},
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-email",
                        "name": "send_email",
                        "arguments": {
                            "to": "buyer@example.com",
                            "subject": "پیشنهاد",
                            "body": "سلام",
                        },
                    }
                ],
            },
            {
                "content": "گزارش: ایمیل پس از تأیید ارسال نشد چون SMTP تنظیم نیست.",
                "tool_calls": [],
            },
        ]
    )
    try:
        import asyncio

        asyncio.run(execute_task(task_id))
    finally:
        scripted_llm.reset(token)
    from app.database import open_session

    db = open_session()
    try:
        task = db.get(AgentTask, task_id)
        assert task is not None
        assert task.status == "waiting_approval", task.error
        approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.task_id == task_id))
        assert approval is not None
        assert approval.status == "pending"
        approval_id = approval.id
    finally:
        db.close()
    decided = client.post(
        f"/api/approvals/{approval_id}/decide",
        headers=headers,
        json={"decision": "approved", "note": "بفرست"},
    )
    assert decided.status_code == 200, decided.text
    _wait_until_done(task_id, {"completed", "failed", "stopped"})
    db = open_session()
    try:
        task = db.get(AgentTask, task_id)
        assert task is not None
        assert task.status == "completed", task.error
        assert "گزارش" in (task.report or "")
        approval = db.get(ApprovalRequest, approval_id)
        assert approval is not None
        assert approval.execution_status in {"executed", "failed"}
        assert "SMTP" in _tool_text(db, task_id) or "ایمیل" in (task.report or "")
    finally:
        db.close()


def _tool_text(db, task_id: str) -> str:
    rows = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id)).all()
    return "\n".join(str(row.payload) for row in rows)


def _user_id(db) -> str:
    from app.models import User

    user = db.scalar(select(User).where(User.email == "admin@example.com"))
    assert user is not None
    return user.id


def _wait_until_done(
    task_id: str,
    statuses: set[str] | None = None,
) -> None:
    from app.database import open_session

    expected = statuses or {"completed", "failed", "stopped", "waiting_approval"}
    for _ in range(80):
        db = open_session()
        try:
            task = db.get(AgentTask, task_id)
            if task and task.status in expected:
                return
        finally:
            db.close()
        time.sleep(0.1)
    raise AssertionError("task did not finish")


def test_agent_row_exists_for_supervisor(client) -> None:
    headers = auth_header(client)
    agents = client.get("/api/agents", headers=headers).json()
    assert any(
        item["slug"] == "supervisor" and "delegate" in item["allowed_tools"] for item in agents
    )
    assert client.get("/api/leads/export.csv", headers=headers).status_code == 200
