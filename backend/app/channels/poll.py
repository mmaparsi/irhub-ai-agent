"""Pull inbound mail, Telegram updates, and Kavenegar inbox. Missing credentials are skipped."""

from __future__ import annotations

import email
import imaplib
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.channels.policy import configured, normalize_address
from app.channels.threads import append_message, ensure_thread
from app.config import settings
from app.models import AgentTask, ChannelState, Conversation
from app.utils import new_id

logger = logging.getLogger(__name__)


def _cursor(db: Session, channel: str) -> str:
    row = db.get(ChannelState, channel)
    return row.cursor if row else ""


def _save_cursor(db: Session, channel: str, cursor: str) -> None:
    row = db.get(ChannelState, channel)
    if row is None:
        db.add(ChannelState(channel=channel, cursor=cursor))
    else:
        row.cursor = cursor
    db.commit()


def poll_all(db: Session) -> dict[str, int]:
    return {
        "email": _safe(db, "email", _poll_email),
        "telegram": _safe(db, "telegram", _poll_telegram),
        "sms": _safe(db, "sms", _poll_sms),
        "whatsapp": 0,
    }


def _safe(db: Session, channel: str, fn) -> int:
    if not configured(channel):
        return 0
    try:
        return int(fn(db))
    except Exception:
        logger.warning("channel poll failed channel=%s", channel)
        return 0


def _store(db: Session, *, channel: str, address: str, body: str, party: str = "customer") -> None:
    thread = ensure_thread(db, channel=channel, address=address, party=party, title=address)
    append_message(db, thread, role="user", content=body, direction="in")
    _maybe_continue(db, thread, address, body)


def _maybe_continue(db: Session, thread: Conversation, address: str, body: str) -> None:
    from app.channels.policy import resolve_policy

    if not thread.agent_id:
        return
    mode, _limit = resolve_policy(db, thread.channel, thread.agent_id)
    if mode != "auto":
        return
    task = AgentTask(
        user_id=thread.user_id,
        agent_id=thread.agent_id,
        goal=(
            f"به این پیام ورودی در کانال {thread.channel} از {address} پاسخ بده. "
            f"شناسه گفتگو {thread.id}. متن:\n{body[:2000]}\n"
            "اگر لازم است با contact_channel جواب بده و داده را جعل نکن."
        ),
        status="queued",
        thread_id="",
        max_steps=6,
    )
    db.add(task)
    db.flush()
    task.thread_id = task.id or new_id()
    db.commit()
    if settings.environment == "test":
        return
    import asyncio

    from app.api.tasks import enqueue_or_spawn

    asyncio.run(enqueue_or_spawn(task.id))


def _poll_email(db: Session) -> int:
    host = settings.imap_host.strip()
    if not host:
        return 0
    client: imaplib.IMAP4
    if settings.imap_ssl:
        client = imaplib.IMAP4_SSL(host, settings.imap_port)
    else:
        client = imaplib.IMAP4(host, settings.imap_port)
    try:
        client.login(settings.imap_user.strip(), settings.imap_password)
        client.select("INBOX")
        _typ, data = client.search(None, "UNSEEN")
        ids = (data[0] or b"").split()
        stored = 0
        for item in ids[:20]:
            _typ, msg_data = client.fetch(item, "(RFC822)")
            raw = msg_data[0][1] if msg_data and isinstance(msg_data[0], tuple) else b""
            parsed = email.message_from_bytes(raw)
            sender = email.utils.parseaddr(parsed.get("From", ""))[1]
            body = _body(parsed)
            if sender and body:
                _store(db, channel="email", address=normalize_address("email", sender), body=body)
                stored += 1
            client.store(item, "+FLAGS", "\\Seen")
        return stored
    finally:
        try:
            client.logout()
        except Exception:
            logger.debug("imap logout failed")


def _body(parsed: email.message.Message) -> str:
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = parsed.get_payload(decode=True) or b""
    if isinstance(payload, bytes):
        return payload.decode(parsed.get_content_charset() or "utf-8", errors="replace")
    return str(payload)


def _poll_telegram(db: Session) -> int:
    token = settings.telegram_bot_token.strip()
    offset = _cursor(db, "telegram")
    params: dict[str, Any] = {"timeout": 0}
    if offset:
        params["offset"] = int(offset)
    response = httpx.get(
        f"https://api.telegram.org/bot{token}/getUpdates", params=params, timeout=20
    )
    response.raise_for_status()
    updates = response.json().get("result") or []
    last = offset
    stored = 0
    for update in updates:
        last = str(int(update.get("update_id", 0)) + 1)
        message = update.get("message") or {}
        text = message.get("text") or ""
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        if chat_id and text:
            _store(db, channel="telegram", address=chat_id, body=text)
            stored += 1
    if last and last != offset:
        _save_cursor(db, "telegram", last)
    return stored


def _poll_sms(db: Session) -> int:
    key = settings.kavenegar_api_key.strip()
    response = httpx.post(
        f"https://api.kavenegar.com/v1/{key}/sms/receive.json",
        data={"linenumber": settings.kavenegar_sender.strip(), "isread": 0},
        timeout=20,
    )
    if response.status_code >= 400:
        return 0
    rows = (
        (response.json().get("entries") or [])
        if response.headers.get("content-type", "").startswith("application/json")
        else []
    )
    stored = 0
    for row in rows:
        sender = str(row.get("sender") or "")
        body = str(row.get("message") or "")
        if sender and body:
            _store(db, channel="sms", address=sender, body=body)
            stored += 1
    return stored


def ingest_whatsapp(db: Session, payload: dict) -> int:
    stored = 0
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                sender = str(message.get("from") or "")
                text = ((message.get("text") or {}).get("body")) or ""
                if sender and text:
                    _store(db, channel="whatsapp", address=sender, body=text)
                    stored += 1
    return stored
