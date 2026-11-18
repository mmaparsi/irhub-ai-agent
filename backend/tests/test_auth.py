from __future__ import annotations

from tests.conftest import auth_header


def test_login_and_me(client) -> None:
    headers = auth_header(client)
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "admin"
    bad = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong-pass"},
    )
    assert bad.status_code == 401


def test_missing_and_invalid_token(client) -> None:
    assert client.get("/api/agents").status_code == 401
    assert (
        client.get("/api/agents", headers={"Authorization": "Bearer not-a-token"}).status_code
        == 401
    )


def test_health_is_public(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mock_llm"] is True


def test_viewer_cannot_manage_agents_or_users(client) -> None:
    admin = auth_header(client)
    created = client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "viewer@example.com",
            "password": "viewer123",
            "full_name": "بیننده",
            "role": "viewer",
        },
    )
    assert created.status_code == 201
    viewer = auth_header(client, "viewer@example.com", "viewer123")
    assert client.get("/api/users", headers=viewer).status_code == 403
    denied = client.post(
        "/api/agents",
        headers=viewer,
        json={
            "slug": "quality_review",
            "name": "Quality",
            "name_fa": "کنترل کیفیت",
            "system_prompt": "تو کارشناس کیفیت هستی.",
            "allowed_tools": [],
            "model_strong": "test/strong",
            "model_fast": "test/fast",
        },
    )
    assert denied.status_code == 403
    allowed = client.post(
        "/api/agents",
        headers=admin,
        json={
            "slug": "quality_review",
            "name": "Quality",
            "name_fa": "کنترل کیفیت",
            "description": "عامل اضافه‌شده از پنل",
            "system_prompt": "تو کارشناس کیفیت هستی و به فارسی جواب می‌دهی.",
            "allowed_tools": ["knowledge_search"],
            "model_strong": "test/strong",
            "model_fast": "test/fast",
        },
    )
    assert allowed.status_code == 201
    listing = client.get("/api/agents", headers=viewer)
    assert listing.status_code == 200
    assert any(item["slug"] == "quality_review" for item in listing.json())
    seeded = {item["slug"] for item in listing.json()}
    assert {"research", "lead_generation", "sales_negotiation", "consulting"} <= seeded


def test_chat_streams_mock_reply_and_task_uses_graph(client) -> None:
    headers = auth_header(client)
    agents = client.get("/api/agents", headers=headers).json()
    research = next(item for item in agents if item["slug"] == "research")
    created = client.post(
        "/api/conversations",
        headers=headers,
        json={"agent_id": research["id"], "title": "آزمایش"},
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    with client.stream(
        "POST",
        f"/api/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "سلام، بازار ورق را جستجو کن", "tier": "fast"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert "data:" in body
    assert "تحقیق بازار" in body
    task = client.post(
        "/api/tasks",
        headers=headers,
        json={"task": "چند سرنخ برای صنایع بسته‌بندی پیدا کن"},
    )
    assert task.status_code == 200, task.text
    payload = task.json()
    assert payload["agent_slug"] == "lead_generation"
    assert "مشتری‌یابی" in payload["result"]
    assert payload["conversation_id"]
