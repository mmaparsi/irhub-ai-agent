from __future__ import annotations

import os
import uuid

os.environ["SKIP_STARTUP_SEED"] = "1"
os.environ["SKIP_REDIS"] = "1"
os.environ["MOCK_LLM"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-secret-key-for-unit-tests-only"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "admin123"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.database import open_session
from app.main import app
from app.models import Base
from app.seed import seed_core


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    name = uuid.uuid4().hex
    engine = create_engine(
        f"sqlite:///file:{name}?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    keepalive = engine.connect()
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr("app.database.SessionLocal", factory)
    Base.metadata.create_all(engine)
    session = open_session()
    seed_core(session)
    session.commit()
    session.close()
    with TestClient(app) as test_client:
        yield test_client
    keepalive.close()
    engine.dispose()


def auth_header(
    client: TestClient, email: str = "admin@example.com", password: str = "admin123"
) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
