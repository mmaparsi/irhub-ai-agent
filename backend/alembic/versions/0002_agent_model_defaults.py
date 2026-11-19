"""Track which agent models are still automatic defaults.

Revision ID: 0002_agent_model_defaults
Revises: 0001_initial
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_agent_model_defaults"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL marks rows seeded before this flag. Startup may replace those
    # models only when they still match a shipped default and that provider
    # has no API key.
    op.execute("ALTER TABLE agents ADD COLUMN model_strong_is_default BOOLEAN")
    op.execute("ALTER TABLE agents ADD COLUMN model_fast_is_default BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS model_fast_is_default")
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS model_strong_is_default")
