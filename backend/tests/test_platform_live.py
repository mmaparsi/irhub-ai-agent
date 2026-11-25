from __future__ import annotations

import pytest

from app.config import settings
from app.models import ApprovalRequest
from app.tools.base import ToolContext, tool_registry
from app.tools.social import build_query, extract_hit, reserve_playwright_slot, social_provider
from tests.conftest import auth_header


def test_roles_split_leads_and_agents(client) -> None:
    sales = auth_header(client, "sales@example.com", "sales12345")
    supplier = auth_header(client, "supplier@example.com", "supplier12345")
    sales_leads = client.get("/api/leads", headers=sales)
    assert sales_leads.status_code == 200
    assert sales_leads.json()
    assert {item["party"] for item in sales_leads.json()} == {"customer"}
    supplier_leads = client.get("/api/leads", headers=supplier).json()
    assert supplier_leads
    assert {item["party"] for item in supplier_leads} == {"supplier"}
    hidden = client.get(f"/api/leads/{sales_leads.json()[0]['id']}", headers=supplier)
    assert hidden.status_code == 404
    agents = client.get("/api/agents", headers=sales).json()
    assert {item["slug"] for item in agents} == {
        "lead_generation",
        "sales_negotiation",
        "supervisor",
    }
    research = next(
        item["id"]
        for item in client.get("/api/agents", headers=auth_header(client)).json()
        if item["slug"] == "research"
    )
    denied = client.post(
        "/api/agent-tasks",
        headers=sales,
        json={"agent_id": research, "goal": "بازار ورق را بررسی کن"},
    )
    assert denied.status_code == 403
    assert client.get("/api/users", headers=sales).status_code == 403


def test_websocket_replays_and_receives_live_events(client) -> None:
    headers = auth_header(client)
    token = headers["Authorization"].split(" ", 1)[1]
    agents = client.get("/api/agents", headers=headers).json()
    agent = next(item for item in agents if item["slug"] == "lead_generation")
    created = client.post(
        "/api/agent-tasks",
        headers=headers,
        json={"agent_id": agent["id"], "goal": "یک سرنخ آزمایشی بساز", "max_steps": 3},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    with client.websocket_connect(f"/api/ws?token={token}") as socket:
        socket.send_json({"action": "subscribe", "task_id": task_id, "after_seq": 0})
        kinds = []
        last = 0
        while True:
            message = socket.receive_json()
            if message["type"] == "subscribed":
                last = message["last_seq"]
                break
            if message["type"] == "task":
                kinds.append(message["kind"])
        assert "plan" in kinds
        assert "status" in kinds
        assert last >= 1
        from app.database import open_session
        from app.runtime.events import emit_event

        db = open_session()
        try:
            emit_event(db, task_id, "status", {"status": "ping"}, dedupe_key="live-ping")
        finally:
            db.close()
        live = socket.receive_json()
        assert live["type"] == "task"
        assert live["kind"] == "status"
        assert live["payload"]["status"] == "ping"
        assert live["seq"] > last


def test_channel_policy_skip_opt_out_and_limit(client, monkeypatch: pytest.MonkeyPatch) -> None:
    admin = auth_header(client)
    listed = client.get("/api/channels", headers=admin)
    assert listed.status_code == 200
    email = next(item for item in listed.json() if item["channel"] == "email")
    assert email["configured"] is False
    assert email["mode"] == "approval"
    assert "password" not in listed.text.lower()
    assert "token" not in listed.text.lower() or "webhook" not in listed.text
    sales = auth_header(client, "sales@example.com", "sales12345")
    assert (
        client.patch(
            "/api/channels/email", headers=sales, json={"mode": "auto", "daily_limit": 1}
        ).status_code
        == 403
    )
    updated = client.patch(
        "/api/channels/email", headers=admin, json={"mode": "auto", "daily_limit": 1}
    )
    assert updated.status_code == 200
    assert updated.json()["mode"] == "auto"

    from app.database import open_session
    from app.runtime.gates import run_gated_tool

    db = open_session()
    try:
        tool = tool_registry.get("contact_channel")
        skipped = run_gated_tool(
            tool,
            {"channel": "telegram", "to": "100", "body": "سلام"},
            ToolContext(db=db, user_id="user"),
            "call-skip",
        )
        assert skipped.ok
        assert skipped.data["code"] == "not_configured"
        assert db.query(ApprovalRequest).count() == 0
    finally:
        db.close()

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "bot@example.com")
    from app.channels.delivery import SendResult

    monkeypatch.setattr(
        "app.channels.tool.dispatch",
        lambda channel, **kwargs: SendResult(True, f"{channel} ارسال شد"),
    )
    from app.channels.policy import evaluate_send

    db = open_session()
    try:
        opted = client.post(
            "/api/channels/opt-outs",
            headers=admin,
            json={"channel": "email", "address": "stop@example.com"},
        )
        assert opted.status_code == 201
        blocked = evaluate_send(db, channel="email", address="stop@example.com", agent_id=None)
        assert blocked.action == "block"
        assert blocked.code == "opt_out"
        allowed = evaluate_send(db, channel="email", address="ok@example.com", agent_id=None)
        assert allowed.action == "auto"
        tool = tool_registry.get("contact_channel")
        sent = run_gated_tool(
            tool,
            {"channel": "email", "to": "ok@example.com", "subject": "سلام", "body": "متن"},
            ToolContext(db=db, user_id="user"),
            "call-auto",
        )
        assert sent.ok
        assert db.query(ApprovalRequest).count() == 0
        again = evaluate_send(db, channel="email", address="next@example.com", agent_id=None)
        assert again.action == "block"
        assert again.code == "daily_limit"
    finally:
        db.close()


def test_public_social_query_and_playwright_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    assert build_query("linkedin", "ورق فولاد", "company").startswith("site:linkedin.com/company")
    assert build_query("linkedin", "مدیر خرید", "person").startswith("site:linkedin.com/in")
    assert build_query("facebook", "بسته بندی", "company").startswith("site:facebook.com")
    profile = extract_hit(
        "linkedin",
        {
            "title": "فولاد البرز | LinkedIn",
            "url": "https://www.linkedin.com/company/alborz",
            "snippet": "صنعت فلزات در تهران https://alborz.example info@alborz.example",
        },
    )
    assert profile["name"] == "فولاد البرز"
    assert profile["location"] == "تهران"
    assert profile["website"] == "https://alborz.example"
    assert profile["emails"] == ["info@alborz.example"]
    assert profile["source"] == "linkedin"
    monkeypatch.setattr(settings, "social_playwright_enabled", False)
    assert social_provider().name == "public_web"
    monkeypatch.setattr(settings, "social_playwright_enabled", True)
    monkeypatch.setattr(settings, "social_session_cookies", "")
    assert social_provider().name == "public_web"
    monkeypatch.setattr(settings, "social_session_cookies", "[]")
    assert social_provider().name == "playwright_session"
    from app.tools import social

    social._playwright_hits.clear()
    monkeypatch.setattr(settings, "social_playwright_hourly_limit", 1)
    monkeypatch.setattr(settings, "social_playwright_min_seconds", 0)
    reserve_playwright_slot()
    with pytest.raises(RuntimeError):
        reserve_playwright_slot()
