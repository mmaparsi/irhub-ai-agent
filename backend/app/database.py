from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

if engine.dialect.name == "postgresql":
    from pgvector.psycopg import register_vector

    @event.listens_for(engine, "connect")
    def _register_vector(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        register_vector(dbapi_connection)


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def open_session() -> Session:
    """Open a session from the current factory.

    Callers use this helper (not a captured SessionLocal) so tests can
    replace `SessionLocal` and reach background and streaming code paths.
    """
    return SessionLocal()


def get_db() -> Iterator[Session]:
    db = open_session()
    try:
        yield db
    finally:
        db.close()
