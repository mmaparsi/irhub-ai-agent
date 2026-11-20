"""Send one message. Credentials stay in the environment and are never logged."""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    ok: bool
    message: str


def dispatch(channel: str, *, to: str, body: str, subject: str = "") -> SendResult:
    try:
        if channel == "email":
            return _email(to, subject or "پیام", body)
        if channel == "telegram":
            return _telegram(to, body)
        if channel == "whatsapp":
            return _whatsapp(to, body)
        if channel == "sms":
            return _sms(to, body)
    except Exception:
        logger.warning("channel send failed channel=%s", channel)
        return SendResult(False, f"ارسال {channel} ناموفق بود.")
    return SendResult(False, f"کانال {channel} پشتیبانی نمی‌شود.")


def _email(to: str, subject: str, body: str) -> SendResult:
    if not (settings.smtp_host.strip() and settings.smtp_from.strip()):
        return SendResult(
            False,
            "ایمیل ارسال نشد: SMTP_HOST و SMTP_FROM تنظیم نشده‌اند. "
            "متن فقط به‌عنوان پیش‌نویس تأییدشده باقی ماند.",
        )
    message = EmailMessage()
    message["From"] = settings.smtp_from.strip()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host.strip(), settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user.strip():
            smtp.login(settings.smtp_user.strip(), settings.smtp_password)
        smtp.send_message(message)
    return SendResult(True, f"ایمیل به {to} ارسال شد.")


def _telegram(chat_id: str, body: str) -> SendResult:
    token = settings.telegram_bot_token.strip()
    if not token:
        return SendResult(False, "کانال telegram تنظیم نشده است.")
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": body},
        timeout=20,
    )
    if response.status_code >= 400:
        return SendResult(False, "ارسال تلگرام ناموفق بود.")
    return SendResult(True, f"پیام تلگرام به {chat_id} ارسال شد.")


def _whatsapp(to: str, body: str) -> SendResult:
    token = settings.whatsapp_token.strip()
    phone_id = settings.whatsapp_phone_id.strip()
    if not token or not phone_id:
        return SendResult(False, "کانال whatsapp تنظیم نشده است.")
    response = httpx.post(
        f"https://graph.facebook.com/v21.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        },
        timeout=20,
    )
    if response.status_code >= 400:
        return SendResult(False, "ارسال واتساپ ناموفق بود.")
    return SendResult(True, f"پیام واتساپ به {to} ارسال شد.")


def _sms(to: str, body: str) -> SendResult:
    key = settings.kavenegar_api_key.strip()
    if not key:
        return SendResult(False, "کانال sms تنظیم نشده است.")
    response = httpx.post(
        f"https://api.kavenegar.com/v1/{key}/sms/send.json",
        data={"receptor": to, "message": body, "sender": settings.kavenegar_sender.strip()},
        timeout=20,
    )
    if response.status_code >= 400:
        return SendResult(False, "ارسال پیامک ناموفق بود.")
    return SendResult(True, f"پیامک به {to} ارسال شد.")
