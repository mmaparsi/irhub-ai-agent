from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.service import request_approval
from app.audit import write_audit
from app.auth.deps import get_current_user, require_roles
from app.database import get_db
from app.models import Agent, ApprovalRequest, User
from app.rules.business import BusinessRuleError
from app.schemas import ApprovalIn, ApprovalOut, DecisionIn
from app.utils import utcnow
from app.worker.jobs import execute_approval_sync
from app.worker.queue import enqueue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["approvals"])


def _out(db: Session, row: ApprovalRequest) -> ApprovalOut:
    requester = db.get(User, row.requested_by) if row.requested_by else None
    agent = db.get(Agent, row.agent_id) if row.agent_id else None
    return ApprovalOut(
        id=row.id,
        action_type=row.action_type,
        payload=row.payload or {},
        status=row.status,
        execution_status=row.execution_status,
        decision_note=row.decision_note or "",
        rule_snapshot=row.rule_snapshot or {},
        created_at=row.created_at,
        decided_at=row.decided_at,
        executed_at=row.executed_at,
        requested_by_name=requester.full_name if requester else None,
        agent_name=agent.name_fa if agent else None,
    )


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ApprovalOut]:
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    return [_out(db, row) for row in db.scalars(stmt.limit(100)).all()]


@router.post("", response_model=ApprovalOut, status_code=201)
def create_approval(
    body: ApprovalIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "expert")),
) -> ApprovalOut:
    try:
        row = request_approval(
            db,
            action_type=body.action_type,
            payload=body.payload,
            user_id=user.id,
            conversation_id=body.conversation_id,
            agent_id=body.agent_id,
        )
    except BusinessRuleError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc
    db.commit()
    db.refresh(row)
    return _out(db, row)


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide(
    approval_id: str,
    body: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "expert")),
) -> ApprovalOut:
    row = db.get(ApprovalRequest, approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="درخواست پیدا نشد")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="این درخواست قبلاً تعیین تکلیف شده است")
    row.status = body.decision
    row.decided_by = user.id
    row.decided_at = utcnow()
    row.decision_note = body.note.strip()
    if body.decision == "approved":
        row.execution_status = "queued"
    else:
        row.execution_status = "skipped"
    write_audit(
        db,
        actor_id=user.id,
        action=f"approval.{body.decision}",
        entity_type="approval_request",
        entity_id=row.id,
        details={},
    )
    db.commit()
    if body.decision == "approved":
        queued = await enqueue("execute_approval", row.id)
        if not queued:
            logger.info("running approval inline because the queue is unavailable")
            execute_approval_sync(row.id)
            db.refresh(row)
    return _out(db, row)
