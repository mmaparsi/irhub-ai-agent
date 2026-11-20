"""Per-channel send policy: approval by default, optional auto-send, daily cap, opt-out."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ChannelPolicy, OptOut, OutreachLog

CHANNELS = ("email", "telegram", "whatsapp", "sms")


@dataclass
class Decision:
    action: str
    message: str = ""
    code: str = ""


def configured(channel: str) -> bool:
    if channel == "email":
        return bool(settings.smtp_host.strip() and settings.smtp_from.strip())
    if channel == "telegram":
        return bool(settings.telegram_bot_token.strip())
    if channel == "whatsapp":
        return bool(settings.whatsapp_token.strip() and settings.whatsapp_phone_id.strip())
    if channel == "sms":
        return bool(settings.kavenegar_api_key.strip())
    return False


def normalize_address(channel: str, address: str) -> str:
    text = (address or "").strip()
    if channel == "email":
        return text.lower()
    return text


def resolve_policy(db: Session, channel: str, agent_id: str | None) -> tuple[str, int]:
    specific = None
    if agent_id:
        specific = db.scalar(
            select(ChannelPolicy).where(
                ChannelPolicy.channel == channel, ChannelPolicy.agent_id == agent_id
            )
        )
    shared = db.scalar(
        select(ChannelPolicy).where(
            ChannelPolicy.channel == channel, ChannelPolicy.agent_id.is_(None)
        )
    )
    row = specific or shared
    if row is None:
        return "approval", settings.channel_daily_limit
    return row.mode or "approval", int(row.daily_limit or settings.channel_daily_limit)


def sent_today(db: Session, channel: str) -> int:
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.scalars(
        select(OutreachLog).where(OutreachLog.channel == channel, OutreachLog.direction == "out")
    ).all()
    count = 0
    for row in rows:
        created = row.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created >= start and row.status == "sent":
            count += 1
    return count


def opted_out(db: Session, channel: str, address: str) -> bool:
    target = normalize_address(channel, address)
    if not target:
        return False
    rows = db.scalars(select(OptOut).where(OptOut.channel == channel)).all()
    return any(normalize_address(channel, row.address) == target for row in rows)


def evaluate_send(db: Session, *, channel: str, address: str, agent_id: str | None) -> Decision:
    if channel not in CHANNELS:
        return Decision("skip", f"کانال {channel} شناخته نشد.", "unknown_channel")
    if not configured(channel):
        return Decision("skip", f"کانال {channel} تنظیم نشده است و ارسال رد شد.", "not_configured")
    if opted_out(db, channel, address):
        return Decision("block", "گیرنده انصراف داده و پیامی ارسال نمی‌شود.", "opt_out")
    mode, limit = resolve_policy(db, channel, agent_id)
    if sent_today(db, channel) >= limit:
        return Decision("block", "سقف ارسال امروز این کانال پر شده است.", "daily_limit")
    if mode == "auto":
        return Decision("auto")
    return Decision("approval")


def record_send(
    db: Session,
    *,
    channel: str,
    address: str,
    body: str,
    status: str,
    agent_id: str | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
    direction: str = "out",
) -> OutreachLog:
    row = OutreachLog(
        channel=channel,
        direction=direction,
        address=normalize_address(channel, address),
        body=body[:8000],
        status=status,
        agent_id=agent_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    db.add(row)
    db.commit()
    return row
