"""Pause the graph for outbound tools, then perform the action after approval."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approvals.service import request_approval
from app.models import ApprovalRequest
from app.rules.business import BusinessRuleError
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.smtp import send_email_smtp
from app.utils import utcnow


def _find(db: Session, task_id: str | None, call_id: str) -> ApprovalRequest | None:
    if not task_id:
        return None
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.task_id == task_id)).all()
    for row in rows:
        if (row.payload or {}).get("call_id") == call_id:
            return row
    return None


def run_gated_tool(
    tool: Tool, arguments: dict[str, Any], context: ToolContext, call_id: str
) -> ToolResult:
    if context.db is None:
        return ToolResult(ok=False, content="پایگاه داده برای تأیید در دسترس نیست.")
    db = context.db
    existing = _find(db, context.task_id, call_id)
    if existing is None:
        payload = {**arguments, "call_id": call_id, "handled_by_graph": True}
        try:
            existing = request_approval(
                db,
                action_type=tool.action_type,  # type: ignore[attr-defined]
                payload=payload,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                agent_id=context.agent_id,
                task_id=context.task_id,
            )
        except BusinessRuleError as exc:
            return ToolResult(ok=False, content=exc.message, data={"code": exc.code})
        db.commit()
    decision = interrupt(
        {
            "approval_id": existing.id,
            "action_type": existing.action_type,
            "summary": _summary(existing.action_type, arguments),
        }
    )
    approved = bool(decision and decision.get("approved"))
    if not approved:
        existing.status = existing.status if existing.status == "rejected" else "rejected"
        existing.execution_status = "skipped"
        db.commit()
        return ToolResult(
            ok=False,
            approval_required=True,
            approval_id=existing.id,
            content="کارشناس این اقدام را رد کرد.",
        )
    message = _perform(existing.action_type, arguments)
    existing.execution_status = (
        "executed" if not message.startswith("ایمیل ارسال نشد") else "failed"
    )
    existing.executed_at = utcnow()
    if existing.status == "pending":
        existing.status = "approved"
    db.commit()
    return ToolResult(
        ok=existing.execution_status == "executed",
        approval_id=existing.id,
        content=message,
        data={"approval_id": existing.id},
    )


def _summary(action_type: str, arguments: dict[str, Any]) -> str:
    if action_type == "email":
        return f"ایمیل به {arguments.get('to')}: {arguments.get('subject')}"
    if action_type == "price_offer":
        return f"پیشنهاد قیمت {arguments.get('deal_title')} با تخفیف {arguments.get('discount_percent')}٪"
    return f"پیام به {arguments.get('to')}"


def _perform(action_type: str, arguments: dict[str, Any]) -> str:
    if action_type == "email":
        return send_email_smtp(
            to=str(arguments.get("to") or ""),
            subject=str(arguments.get("subject") or ""),
            body=str(arguments.get("body") or ""),
        )
    if action_type == "price_offer":
        return (
            "پیشنهاد قیمت تأیید شد و در پرونده ماند. "
            f"تخفیف {arguments.get('discount_percent')}٪ از سقف مجاز بیشتر نیست."
        )
    return "متن پیام تأیید شد. اتصال پیام‌رسان هنوز تنظیم نشده و ارسال خارجی انجام نشد."
