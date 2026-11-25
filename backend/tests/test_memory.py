"""Memory tools fall back to text search when embeddings are unavailable."""

from app.config import settings
from app.knowledge.embeddings import try_embed
from app.memory.store import recall, remember
from app.models import Memory
from tests.conftest import auth_header


def test_recall_uses_text_when_embedding_is_missing(client):
    from app.database import open_session
    from app.models import User

    db = open_session()
    try:
        user = db.query(User).filter(User.email == "admin@example.com").one()
        remember(
            db,
            content="تخفیف توافق‌شده با کارخانهٔ البرز ۱۲ درصد است.",
            user_id=user.id,
            agent_type="sales_negotiation",
            entity_type="lead",
            entity_id="lead-1",
            importance=4,
        )
        rows = recall(db, query="البرز", user=user, k=3)
        assert rows
        assert "۱۲" in rows[0].content
        assert rows[0].embedding is None
    finally:
        db.close()


def test_try_embed_returns_none_when_provider_fails(monkeypatch):
    monkeypatch.setattr(settings, "embedding_model", "openai/text-embedding-3-small")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "mock_llm", "false")

    def boom(**kwargs):
        raise RuntimeError("embedding down")

    import litellm

    monkeypatch.setattr(litellm, "embedding", boom)
    assert try_embed("یک واقعیت") is None


def test_sales_cannot_see_supplier_agent_memory(client):
    from app.database import open_session
    from app.models import User

    db = open_session()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").one()
        remember(
            db,
            content="تأمین‌کنندهٔ فولاد قیمت را قطعی کرد.",
            user_id=admin.id,
            agent_type="consulting",
            entity_type="supplier",
            importance=2,
        )
        remember(
            db,
            content="مشتری مبلمان پیگیری می‌خواهد.",
            user_id=admin.id,
            agent_type="sales_negotiation",
            entity_type="customer",
            importance=2,
        )
    finally:
        db.close()
    sales = auth_header(client, "sales@example.com", "sales12345")
    listed = client.get("/api/memories", headers=sales)
    assert listed.status_code == 200
    texts = [row["content"] for row in listed.json()]
    assert any("مبلمان" in text for text in texts)
    assert all("فولاد" not in text for text in texts)
    admin_header = auth_header(client)
    everything = client.get("/api/memories", headers=admin_header)
    assert any("فولاد" in row["content"] for row in everything.json())


def test_delete_memory(client):
    from app.database import open_session
    from app.models import User

    db = open_session()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com").one()
        row = remember(db, content="یادداشت موقت", user_id=admin.id, agent_type="research")
        memory_id = row.id
    finally:
        db.close()
    response = client.delete(f"/api/memories/{memory_id}", headers=auth_header(client))
    assert response.status_code == 204
    db = open_session()
    try:
        assert db.get(Memory, memory_id) is None
    finally:
        db.close()
