from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.audit import write_audit
from app.models import ApprovalRequest
from app.rules.business import enforce_outbound_rules


def request_approval(
    db: Session,
    *,
    action_type: str,
    payload: dict[str, Any],
    user_id: str | None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
) -> ApprovalRequest:
    """Persist a pending approval. Rules run before the row is created.

    Nothing is sent from here. Execution happens only after an expert approves,
    and even then the worker calls a stub provider.
    """
    snapshot = enforce_outbound_rules(action_type, payload)
    row = ApprovalRequest(
        action_type=action_type,
        payload=payload,
        status="pending",
        execution_status="not_started",
        requested_by=user_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
        rule_snapshot=snapshot,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        actor_id=user_id,
        action="approval.requested",
        entity_type="approval_request",
        entity_id=row.id,
        details={"action_type": action_type},
    )
    return row
