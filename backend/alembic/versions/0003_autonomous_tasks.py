"""Tasks, events, artifacts, and long-term memory.

Revision ID: 0003_autonomous_tasks
Revises: 0002_agent_model_defaults
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_autonomous_tasks"
down_revision: str | None = "0002_agent_model_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_tasks (
            id VARCHAR(36) NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            agent_id VARCHAR(36),
            goal TEXT NOT NULL,
            status VARCHAR(32) NOT NULL,
            thread_id VARCHAR(64) NOT NULL,
            plan TEXT NOT NULL,
            report TEXT NOT NULL,
            step INTEGER NOT NULL,
            max_steps INTEGER NOT NULL,
            error TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            finished_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            UNIQUE (thread_id),
            FOREIGN KEY(user_id) REFERENCES users (id),
            FOREIGN KEY(agent_id) REFERENCES agents (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_agent_tasks_user_id ON agent_tasks (user_id)")
    op.execute("CREATE INDEX ix_agent_tasks_status ON agent_tasks (status)")
    op.execute(
        """
        CREATE TABLE task_events (
            id VARCHAR(36) NOT NULL,
            task_id VARCHAR(36) NOT NULL,
            seq INTEGER NOT NULL,
            kind VARCHAR(32) NOT NULL,
            payload JSON NOT NULL,
            dedupe_key VARCHAR(128),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(task_id) REFERENCES agent_tasks (id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_task_events_task_id ON task_events (task_id)")
    op.execute(
        """
        CREATE TABLE artifacts (
            id VARCHAR(36) NOT NULL,
            task_id VARCHAR(36),
            filename VARCHAR(255) NOT NULL,
            media_type VARCHAR(128) NOT NULL,
            path VARCHAR(512) NOT NULL,
            size INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(task_id) REFERENCES agent_tasks (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_artifacts_task_id ON artifacts (task_id)")
    op.execute(
        """
        CREATE TABLE agent_memories (
            id VARCHAR(36) NOT NULL,
            user_id VARCHAR(36),
            kind VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR(1536),
            metadata JSON NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES users (id)
        )
        """
    )
    op.execute("ALTER TABLE approval_requests ADD COLUMN task_id VARCHAR(36)")
    op.execute("CREATE INDEX ix_approval_requests_task_id ON approval_requests (task_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_approval_requests_task_id")
    op.execute("ALTER TABLE approval_requests DROP COLUMN IF EXISTS task_id")
    op.execute("DROP TABLE IF EXISTS agent_memories")
    op.execute("DROP TABLE IF EXISTS artifacts")
    op.execute("DROP TABLE IF EXISTS task_events")
    op.execute("DROP TABLE IF EXISTS agent_tasks")
