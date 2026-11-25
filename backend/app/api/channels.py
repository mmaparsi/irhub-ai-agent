from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_roles, require_staff
from app.channels.policy import CHANNELS, configured, resolve_policy, sent_today
from app.channels.poll import ingest_whatsapp, poll_all
from app.config import settings
from app.database import get_db
from app.models import ChannelPolicy, OptOut, User

router = APIRouter(prefix="/channels", tags=["channels"])

LABELS = {
    "email": "ایمیل",
    "telegram": "تلگرام",
    "whatsapp": "واتساپ",
    "sms": "پیامک",
}


class PolicyIn(BaseModel):
    mode: str = Field(pattern="^(approval|auto)$")
    daily_limit: int = Field(ge=0, le=500)


class OptOutIn(BaseModel):
    channel: str
    address: str = Field(min_length=1, max_length=255)


def _status(db: Session, channel: str) -> dict:
    mode, limit = resolve_policy(db, channel, None)
    return {
        "channel": channel,
        "label": LABELS.get(channel, channel),
        "configured": configured(channel),
        "mode": mode,
        "daily_limit": limit,
        "sent_today": sent_today(db, channel),
    }


@router.get("")
def list_channels(
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
) -> list[dict]:
    return [_status(db, channel) for channel in CHANNELS]


@router.patch("/{channel}")
def update_policy(
    channel: str,
    body: PolicyIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    if channel not in CHANNELS:
        raise HTTPException(status_code=404, detail="کانال پیدا نشد")
    row = db.scalar(
        select(ChannelPolicy).where(
            ChannelPolicy.channel == channel, ChannelPolicy.agent_id.is_(None)
        )
    )
    if row is None:
        row = ChannelPolicy(channel=channel, agent_id=None)
        db.add(row)
    row.mode = body.mode
    row.daily_limit = body.daily_limit
    db.commit()
    return _status(db, channel)


@router.get("/opt-outs")
def list_opt_outs(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> list[dict]:
    rows = db.scalars(select(OptOut).order_by(OptOut.created_at.desc())).all()
    return [{"id": row.id, "channel": row.channel, "address": row.address} for row in rows]


@router.post("/opt-outs", status_code=201)
def add_opt_out(
    body: OptOutIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
) -> dict:
    if body.channel not in CHANNELS:
        raise HTTPException(status_code=422, detail="کانال نامعتبر است")
    row = OptOut(channel=body.channel, address=body.address.strip())
    db.add(row)
    db.commit()
    return {"id": row.id, "channel": row.channel, "address": row.address}


@router.post("/poll")
def poll_channels(
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict:
    return poll_all(db)


@router.get("/whatsapp/webhook")
def whatsapp_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> PlainTextResponse:
    expected = settings.whatsapp_webhook_token.strip()
    if not expected or hub_mode != "subscribe" or hub_verify_token != expected:
        raise HTTPException(status_code=403, detail="تأیید وب‌هوک نامعتبر است")
    return PlainTextResponse(hub_challenge)


@router.post("/whatsapp/webhook")
async def whatsapp_inbound(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
) -> dict:
    expected = settings.whatsapp_webhook_token.strip()
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="وب‌هوک نامعتبر است")
    payload = await request.json()
    stored = ingest_whatsapp(db, payload if isinstance(payload, dict) else {})
    return {"stored": stored}
