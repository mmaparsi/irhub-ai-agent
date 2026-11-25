"""Parent link for supervisor child tasks.

Revision ID: 0006_task_tree
Revises: 0005_memories
Create Date: 2026-11-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_task_tree"
down_revision: str | None = "0005_memories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_tasks ADD COLUMN parent_task_id VARCHAR(36)")
    op.execute("ALTER TABLE agent_tasks ADD COLUMN depth INTEGER NOT NULL DEFAULT 0")
    op.execute("CREATE INDEX ix_agent_tasks_parent_task_id ON agent_tasks (parent_task_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_tasks_parent_task_id")
    op.execute("ALTER TABLE agent_tasks DROP COLUMN IF EXISTS depth")
    op.execute("ALTER TABLE agent_tasks DROP COLUMN IF EXISTS parent_task_id")
