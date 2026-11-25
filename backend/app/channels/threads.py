"""One thread per contact per channel, plus inbound storage."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message, User
from app.realtime import hub


def _next_seq(db: Session, conversation_id: str) -> int:
    current = db.scalar(
        select(Message.seq)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.desc())
        .limit(1)
    )
    return int(current or 0) + 1


def _owner(db: Session, party: str) -> User | None:
    role = "supplier_acquisition" if party == "supplier" else "sales"
    user = db.scalar(select(User).where(User.role == role, User.is_active.is_(True)))
    if user is None:
        user = db.scalar(select(User).where(User.role == "admin", User.is_active.is_(True)))
    return user


def ensure_thread(
    db: Session,
    *,
    channel: str,
    address: str,
    party: str = "customer",
    user_id: str | None = None,
    agent_id: str | None = None,
    lead_id: str | None = None,
    title: str = "",
) -> Conversation:
    key = f"{channel}:{address.strip().lower() if channel == 'email' else address.strip()}"
    row = db.scalar(
        select(Conversation).where(
            Conversation.channel == channel, Conversation.external_key == key
        )
    )
    if row is not None:
        return row
    owner = user_id
    if owner is not None and db.get(User, owner) is None:
        owner = None
    if owner is None:
        user = _owner(db, party)
        owner = user.id if user else None
    if owner is None:
        raise RuntimeError("no user for channel thread")
    row = Conversation(
        user_id=owner,
        agent_id=agent_id,
        title=title or f"{channel} · {address}",
        status="open",
        channel=channel,
        party=party,
        lead_id=lead_id,
        external_key=key,
    )
    db.add(row)
    db.flush()
    return row


def append_message(
    db: Session,
    conversation: Conversation,
    *,
    role: str,
    content: str,
    direction: str,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        seq=_next_seq(db, conversation.id),
        role=role,
        direction=direction,
        content=content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    hub.publish(
        {
            "type": "activity",
            "seq": message.seq,
            "kind": "message",
            "payload": {
                "conversation_id": conversation.id,
                "channel": conversation.channel,
                "direction": direction,
                "preview": content[:180],
            },
            "user_id": conversation.user_id,
            "role": "",
            "task_id": None,
        }
    )
    return message
