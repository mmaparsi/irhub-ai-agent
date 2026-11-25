"""Long-term memories with pgvector and full-text fallback.

Revision ID: 0005_memories
Revises: 0004_roles_channels_live
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_memories"
down_revision: str | None = "0004_roles_channels_live"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE memories (
            id VARCHAR(36) NOT NULL,
            user_id VARCHAR(36),
            agent_type VARCHAR(64) NOT NULL DEFAULT '',
            entity_type VARCHAR(32) NOT NULL DEFAULT 'general',
            entity_id VARCHAR(36),
            content TEXT NOT NULL,
            embedding vector(1536),
            importance INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            last_accessed_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_memories_user_id ON memories (user_id)")
    op.execute("CREATE INDEX ix_memories_entity_type ON memories (entity_type)")
    op.execute("CREATE INDEX ix_memories_entity_id ON memories (entity_id)")
    op.execute(
        "CREATE INDEX ix_memories_fts ON memories USING gin (to_tsvector('simple', content))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memories")
