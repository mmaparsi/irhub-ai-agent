"""Initial schema with pgvector.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# DDL matches app.models. Keep EMBEDDING_DIM (1536) in sync with app.constants.
STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE agents (
        id VARCHAR(36) NOT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(255) NOT NULL,
        name_fa VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        system_prompt TEXT NOT NULL,
        allowed_tools JSON NOT NULL,
        model_strong VARCHAR(255) NOT NULL,
        model_fast VARCHAR(255) NOT NULL,
        temperature FLOAT NOT NULL,
        is_active BOOLEAN NOT NULL,
        config JSON NOT NULL,
        source VARCHAR(32) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    "CREATE UNIQUE INDEX ix_agents_slug ON agents (slug)",
    """
    CREATE TABLE companies (
        id VARCHAR(36) NOT NULL,
        name VARCHAR(255) NOT NULL,
        industry VARCHAR(255) NOT NULL,
        website VARCHAR(255) NOT NULL,
        city VARCHAR(128) NOT NULL,
        notes TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE tools (
        id VARCHAR(36) NOT NULL,
        name VARCHAR(64) NOT NULL,
        description TEXT NOT NULL,
        kind VARCHAR(32) NOT NULL,
        input_schema JSON NOT NULL,
        provider VARCHAR(64) NOT NULL,
        is_enabled BOOLEAN NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    "CREATE UNIQUE INDEX ix_tools_name ON tools (name)",
    """
    CREATE TABLE users (
        id VARCHAR(36) NOT NULL,
        email VARCHAR(255) NOT NULL,
        hashed_password VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) NOT NULL,
        role VARCHAR(32) NOT NULL,
        is_active BOOLEAN NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id)
    )
    """,
    "CREATE UNIQUE INDEX ix_users_email ON users (email)",
    """
    CREATE TABLE audit_log (
        id VARCHAR(36) NOT NULL,
        actor_id VARCHAR(36),
        action VARCHAR(64) NOT NULL,
        entity_type VARCHAR(64) NOT NULL,
        entity_id VARCHAR(36) NOT NULL,
        details JSON NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(actor_id) REFERENCES users (id)
    )
    """,
    "CREATE INDEX ix_audit_log_action ON audit_log (action)",
    """
    CREATE TABLE conversations (
        id VARCHAR(36) NOT NULL,
        user_id VARCHAR(36) NOT NULL,
        agent_id VARCHAR(36),
        title VARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id),
        FOREIGN KEY(agent_id) REFERENCES agents (id)
    )
    """,
    "CREATE INDEX ix_conversations_user_id ON conversations (user_id)",
    """
    CREATE TABLE knowledge_documents (
        id VARCHAR(36) NOT NULL,
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        source VARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        embedding VECTOR(1536),
        metadata JSON NOT NULL,
        uploaded_by VARCHAR(36),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(uploaded_by) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE leads (
        id VARCHAR(36) NOT NULL,
        company_id VARCHAR(36),
        title VARCHAR(255) NOT NULL,
        source VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        score INTEGER NOT NULL,
        notes TEXT NOT NULL,
        created_by VARCHAR(36),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(company_id) REFERENCES companies (id),
        FOREIGN KEY(created_by) REFERENCES users (id)
    )
    """,
    "CREATE INDEX ix_leads_status ON leads (status)",
    """
    CREATE TABLE approval_requests (
        id VARCHAR(36) NOT NULL,
        action_type VARCHAR(32) NOT NULL,
        payload JSON NOT NULL,
        status VARCHAR(32) NOT NULL,
        execution_status VARCHAR(32) NOT NULL,
        requested_by VARCHAR(36),
        decided_by VARCHAR(36),
        conversation_id VARCHAR(36),
        agent_id VARCHAR(36),
        decision_note TEXT NOT NULL,
        rule_snapshot JSON NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        decided_at TIMESTAMP WITH TIME ZONE,
        executed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        FOREIGN KEY(requested_by) REFERENCES users (id),
        FOREIGN KEY(decided_by) REFERENCES users (id),
        FOREIGN KEY(conversation_id) REFERENCES conversations (id),
        FOREIGN KEY(agent_id) REFERENCES agents (id)
    )
    """,
    "CREATE INDEX ix_approval_requests_status ON approval_requests (status)",
    "CREATE INDEX ix_approval_requests_action_type ON approval_requests (action_type)",
    """
    CREATE TABLE contacts (
        id VARCHAR(36) NOT NULL,
        company_id VARCHAR(36),
        lead_id VARCHAR(36),
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) NOT NULL,
        phone VARCHAR(64) NOT NULL,
        title VARCHAR(255) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(company_id) REFERENCES companies (id),
        FOREIGN KEY(lead_id) REFERENCES leads (id)
    )
    """,
    """
    CREATE TABLE deals (
        id VARCHAR(36) NOT NULL,
        lead_id VARCHAR(36),
        title VARCHAR(255) NOT NULL,
        value NUMERIC(18, 2) NOT NULL,
        currency VARCHAR(8) NOT NULL,
        stage VARCHAR(32) NOT NULL,
        discount_percent FLOAT NOT NULL,
        owner_id VARCHAR(36),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(lead_id) REFERENCES leads (id),
        FOREIGN KEY(owner_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE messages (
        id VARCHAR(36) NOT NULL,
        conversation_id VARCHAR(36) NOT NULL,
        seq INTEGER NOT NULL,
        role VARCHAR(32) NOT NULL,
        content TEXT NOT NULL,
        tool_calls JSON,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX ix_messages_conversation_id ON messages (conversation_id)",
]


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "messages",
        "deals",
        "contacts",
        "approval_requests",
        "leads",
        "knowledge_documents",
        "conversations",
        "audit_log",
        "users",
        "tools",
        "companies",
        "agents",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP EXTENSION IF EXISTS vector")
