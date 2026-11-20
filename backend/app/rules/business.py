from __future__ import annotations

from typing import Any

from app.config import settings

OUTBOUND_ACTION_TYPES = frozenset({"email", "message", "price_offer"})
_MAX_TEXT = 20_000


class BusinessRuleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def enforce_outbound_rules(
    action_type: str,
    payload: dict[str, Any],
    *,
    max_discount_percent: float | None = None,
) -> dict[str, Any]:
    """Validate an outbound action. Raise BusinessRuleError to block it.

    The returned snapshot is stored on the approval request so a later change
    to the cap does not rewrite history.
    """
    cap = settings.max_discount_percent if max_discount_percent is None else max_discount_percent
    if not isinstance(payload, dict):
        raise BusinessRuleError("invalid_payload", "بدنهٔ اقدام نامعتبر است.")
    if action_type not in OUTBOUND_ACTION_TYPES:
        raise BusinessRuleError("unknown_outbound_action", "نوع اقدام خروجی مجاز نیست.")

    snapshot: dict[str, Any] = {"action_type": action_type, "max_discount_percent": cap}
    if action_type == "email":
        to = _required_text(payload, "to", "نشانی گیرنده لازم است.")
        if "@" not in to or "." not in to.split("@")[-1]:
            raise BusinessRuleError("invalid_email", "نشانی ایمیل گیرنده نامعتبر است.")
        _required_text(payload, "subject", "موضوع ایمیل لازم است.")
        _required_text(payload, "body", "متن ایمیل لازم است.")
        snapshot["to"] = to
    elif action_type == "message":
        _required_text(payload, "to", "گیرندهٔ پیام لازم است.")
        _required_text(payload, "body", "متن پیام لازم است.")
        channel = str(payload.get("channel") or "other").strip() or "other"
        snapshot["channel"] = channel
    elif action_type == "price_offer":
        title = _required_text(payload, "deal_title", "عنوان پیشنهاد قیمت لازم است.")
        discount = _as_float(payload.get("discount_percent", 0), "درصد تخفیف نامعتبر است.")
        amount = _as_float(payload.get("amount", 0), "مبلغ پیشنهاد نامعتبر است.")
        if discount < 0:
            raise BusinessRuleError("invalid_discount", "درصد تخفیف نمی‌تواند منفی باشد.")
        if discount > cap:
            raise BusinessRuleError(
                "max_discount_exceeded",
                f"تخفیف {discount:g}٪ از سقف مجاز {cap:g}٪ بیشتر است و ثبت نمی‌شود.",
            )
        if amount < 0:
            raise BusinessRuleError("invalid_amount", "مبلغ نمی‌تواند منفی باشد.")
        snapshot["deal_title"] = title
        snapshot["discount_percent"] = discount
        snapshot["amount"] = amount
    return snapshot


def _required_text(payload: dict[str, Any], key: str, message: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise BusinessRuleError("missing_field", message)
    if len(value) > _MAX_TEXT:
        raise BusinessRuleError("payload_too_large", "متن اقدام خروجی بیش از حد بلند است.")
    return value


def _as_float(value: object, message: str) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise BusinessRuleError("invalid_number", message) from None
