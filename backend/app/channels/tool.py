"""Agent tool that contacts a person on a configured channel."""

from __future__ import annotations

from typing import Any

from app.channels.delivery import dispatch
from app.channels.policy import evaluate_send, record_send
from app.channels.threads import append_message, ensure_thread
from app.runtime.events import publish_activity
from app.tools.base import Tool, ToolContext, ToolResult


def channel_action(channel: str) -> str:
    return "email" if channel == "email" else "message"


class ContactChannelTool(Tool):
    name = "contact_channel"
    kind = "outbound"
    action_type = "message"
    description = (
        "گفتگو با مشتری یا تأمین‌کننده از ایمیل، تلگرام، واتساپ یا پیامک. "
        "اگر کانال تنظیم نشده باشد رد می‌شود. پیش‌فرض، تأیید انسان است."
    )
    provider = "channel"
    input_schema = {
        "type": "object",
        "properties": {
            "channel": {"type": "string", "enum": ["email", "telegram", "whatsapp", "sms"]},
            "to": {"type": "string"},
            "body": {"type": "string"},
            "subject": {"type": "string"},
            "lead_id": {"type": "string"},
            "party": {"type": "string", "enum": ["customer", "supplier"]},
        },
        "required": ["channel", "to", "body"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.db is None:
            return ToolResult(ok=False, content="پایگاه داده برای ارسال در دسترس نیست.")
        handled = apply_channel_policy(arguments, context, call_id="")
        if handled is not None:
            return handled
        from app.approvals.service import request_approval
        from app.rules.business import BusinessRuleError

        channel = str(arguments.get("channel") or "")
        try:
            approval = request_approval(
                context.db,
                action_type=channel_action(channel),
                payload=arguments,
                user_id=context.user_id,
                conversation_id=context.conversation_id,
                agent_id=context.agent_id,
                task_id=context.task_id,
            )
        except BusinessRuleError as exc:
            return ToolResult(ok=False, content=exc.message, data={"code": exc.code})
        context.db.commit()
        return ToolResult(
            ok=True,
            approval_required=True,
            approval_id=approval.id,
            content=f"ارسال نشد. درخواست تأیید ثبت شد (شناسه {approval.id}).",
            data={"approval_id": approval.id, "status": "pending"},
        )


def apply_channel_policy(
    arguments: dict[str, Any], context: ToolContext, *, call_id: str
) -> ToolResult | None:
    """Return a result when the send is skipped, blocked, or auto-sent.

    None means the caller should open the normal approval interrupt.
    """
    if context.db is None:
        return ToolResult(ok=False, content="پایگاه داده برای سیاست کانال در دسترس نیست.")
    channel = str(arguments.get("channel") or "").strip().lower()
    address = str(arguments.get("to") or "")
    decision = evaluate_send(
        context.db, channel=channel, address=address, agent_id=context.agent_id
    )
    if decision.action in {"skip", "block"}:
        return ToolResult(
            ok=decision.action == "skip",
            content=decision.message,
            data={"code": decision.code, "call_id": call_id},
        )
    if decision.action == "auto":
        return _send_now(arguments, context)
    return None


def perform_send(arguments: dict[str, Any], context: ToolContext | None = None) -> str:
    channel = str(arguments.get("channel") or "email").strip().lower()
    if "subject" in arguments or channel == "email":
        channel = channel or "email"
    result = dispatch(
        channel,
        to=str(arguments.get("to") or ""),
        body=str(arguments.get("body") or ""),
        subject=str(arguments.get("subject") or ""),
    )
    if context is not None and context.db is not None:
        record_send(
            context.db,
            channel=channel,
            address=str(arguments.get("to") or ""),
            body=str(arguments.get("body") or ""),
            status="sent" if result.ok else "failed",
            agent_id=context.agent_id,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
        )
        if result.ok:
            _log_thread(arguments, context, channel)
    return result.message


def _send_now(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    message = perform_send(arguments, context)
    ok = (
        "ناموفق" not in message
        and not message.startswith("ایمیل ارسال نشد")
        and "تنظیم نشده" not in message
    )
    return ToolResult(ok=ok, content=message, data={"mode": "auto"})


def _log_thread(arguments: dict[str, Any], context: ToolContext, channel: str) -> None:
    if context.db is None:
        return
    party = str(arguments.get("party") or "customer")
    thread = ensure_thread(
        context.db,
        channel=channel,
        address=str(arguments.get("to") or ""),
        party=party,
        user_id=context.user_id,
        agent_id=context.agent_id,
        lead_id=str(arguments.get("lead_id") or "") or None,
    )
    append_message(
        context.db,
        thread,
        role="assistant",
        content=str(arguments.get("body") or ""),
        direction="out",
    )
    publish_activity(
        context.db,
        kind="message",
        payload={"channel": channel, "direction": "out", "to": arguments.get("to")},
        user_id=context.user_id,
        task_id=context.task_id,
    )
