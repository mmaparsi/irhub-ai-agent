from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.audit import write_audit
from app.database import open_session
from app.knowledge.embeddings import embed_text
from app.models import ApprovalRequest, KnowledgeDocument
from app.utils import utcnow

logger = logging.getLogger(__name__)


def execute_approval_sync(approval_id: str) -> str:
    """Run an already-approved outbound action.

    The provider call is a stub: no email, message, or quote is delivered.
    Business rules were enforced when the approval row was created.
    """
    db = open_session()
    try:
        return _execute(db, approval_id)
    except Exception:
        db.rollback()
        logger.exception("approval execution failed id=%s", approval_id)
        _mark_failed(approval_id)
        return "failed"
    finally:
        db.close()


def _execute(db: Session, approval_id: str) -> str:
    row = db.get(ApprovalRequest, approval_id)
    if row is None or row.status != "approved":
        db.rollback()
        return "skipped"
    if row.execution_status == "executed":
        db.rollback()
        return "already"
    if (row.payload or {}).get("handled_by_graph"):
        db.rollback()
        return "graph"
    if row.action_type == "email":
        from app.tools.smtp import send_email_smtp

        message = send_email_smtp(
            to=str(row.payload.get("to") or ""),
            subject=str(row.payload.get("subject") or ""),
            body=str(row.payload.get("body") or ""),
        )
        logger.info("email approval id=%s result=%s", row.id, message)
    else:
        logger.info("approved outbound recorded id=%s type=%s", row.id, row.action_type)
    row.execution_status = "executed"
    row.executed_at = utcnow()
    write_audit(
        db,
        actor_id=row.decided_by,
        action="approval.executed",
        entity_type="approval_request",
        entity_id=row.id,
        details={"action_type": row.action_type, "provider": "stub"},
    )
    db.commit()
    return "executed"


def _mark_failed(approval_id: str) -> None:
    db = open_session()
    try:
        row = db.get(ApprovalRequest, approval_id)
        if row is not None and row.execution_status != "executed":
            row.execution_status = "failed"
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()
        logger.exception("could not mark approval failed id=%s", approval_id)
    finally:
        db.close()


def index_document_sync(document_id: str) -> str:
    db = open_session()
    try:
        document = db.get(KnowledgeDocument, document_id)
        if document is None:
            return "missing"
        document.embedding = embed_text(f"{document.title}\n{document.content}")
        document.status = "ready"
        db.commit()
        return "ready"
    except Exception:
        db.rollback()
        logger.exception("index failed id=%s", document_id)
        return "failed"
    finally:
        db.close()


async def execute_approval(ctx, approval_id: str) -> str:  # noqa: ANN001
    import asyncio

    return await asyncio.to_thread(execute_approval_sync, approval_id)


async def index_document(ctx, document_id: str) -> str:  # noqa: ANN001
    import asyncio

    return await asyncio.to_thread(index_document_sync, document_id)


async def run_agent_task(ctx, task_id: str) -> None:  # noqa: ANN001
    from app.runtime.executor import execute_task

    await execute_task(task_id)


async def resume_agent_task(ctx, task_id: str, decision_json: str) -> None:  # noqa: ANN001
    import json

    from app.runtime.executor import execute_task

    decision = json.loads(decision_json)
    await execute_task(task_id, resume=decision)
