"""Roles, lead party, channels, and live activity.

Revision ID: 0004_roles_channels_live
Revises: 0003_autonomous_tasks
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_roles_channels_live"
down_revision: str | None = "0003_autonomous_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE leads ADD COLUMN party VARCHAR(32) NOT NULL DEFAULT 'customer'")
    op.execute("ALTER TABLE contacts ADD COLUMN party VARCHAR(32) NOT NULL DEFAULT 'customer'")
    op.execute("ALTER TABLE conversations ADD COLUMN channel VARCHAR(32) NOT NULL DEFAULT 'panel'")
    op.execute("ALTER TABLE conversations ADD COLUMN party VARCHAR(32) NOT NULL DEFAULT 'customer'")
    op.execute("ALTER TABLE conversations ADD COLUMN contact_id VARCHAR(36)")
    op.execute("ALTER TABLE conversations ADD COLUMN lead_id VARCHAR(36)")
    op.execute("ALTER TABLE conversations ADD COLUMN external_key VARCHAR(255) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE messages ADD COLUMN direction VARCHAR(16) NOT NULL DEFAULT 'internal'")
    op.execute(
        "UPDATE leads SET party = 'supplier' WHERE title LIKE '%تأمین%' OR title LIKE '%پارچه%'"
    )
    op.execute(
        """
        UPDATE contacts SET party = (
            SELECT leads.party FROM leads WHERE leads.id = contacts.lead_id
        )
        WHERE lead_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE channel_policies (
            id VARCHAR(36) NOT NULL,
            agent_id VARCHAR(36),
            channel VARCHAR(32) NOT NULL,
            mode VARCHAR(16) NOT NULL,
            daily_limit INTEGER NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(agent_id) REFERENCES agents (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_channel_policies_channel ON channel_policies (channel)")
    op.execute(
        """
        CREATE TABLE opt_outs (
            id VARCHAR(36) NOT NULL,
            channel VARCHAR(32) NOT NULL,
            address VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_opt_outs_channel ON opt_outs (channel)")
    op.execute(
        """
        CREATE TABLE outreach_logs (
            id VARCHAR(36) NOT NULL,
            channel VARCHAR(32) NOT NULL,
            direction VARCHAR(8) NOT NULL,
            address VARCHAR(255) NOT NULL,
            body TEXT NOT NULL,
            status VARCHAR(32) NOT NULL,
            agent_id VARCHAR(36),
            user_id VARCHAR(36),
            conversation_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_outreach_logs_channel ON outreach_logs (channel)")
    op.execute(
        """
        CREATE TABLE channel_state (
            channel VARCHAR(32) NOT NULL,
            cursor TEXT NOT NULL,
            PRIMARY KEY (channel)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE activity_events (
            id VARCHAR(36) NOT NULL,
            seq INTEGER NOT NULL,
            kind VARCHAR(32) NOT NULL,
            payload JSON NOT NULL,
            user_id VARCHAR(36),
            role VARCHAR(32) NOT NULL,
            task_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_activity_events_seq ON activity_events (seq)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS activity_events")
    op.execute("DROP TABLE IF EXISTS channel_state")
    op.execute("DROP TABLE IF EXISTS outreach_logs")
    op.execute("DROP TABLE IF EXISTS opt_outs")
    op.execute("DROP TABLE IF EXISTS channel_policies")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS direction")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS external_key")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS lead_id")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS contact_id")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS party")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS channel")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS party")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS party")
