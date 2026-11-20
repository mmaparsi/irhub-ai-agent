"""SMTP delivery used only after an approval is granted."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings


def smtp_configured() -> bool:
    return bool(settings.smtp_host.strip() and settings.smtp_from.strip())


def send_email_smtp(*, to: str, subject: str, body: str) -> str:
    if not smtp_configured():
        return (
            "ایمیل ارسال نشد: SMTP_HOST و SMTP_FROM تنظیم نشده‌اند. "
            "متن فقط به‌عنوان پیش‌نویس تأییدشده باقی ماند."
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
    return f"ایمیل به {to} ارسال شد."
