from app.agents.registry import AgentSpec
from app.config import settings

_strong, _fast = settings.resolved_model_defaults()

SPEC = AgentSpec(
    slug="sales_negotiation",
    name="Sales Negotiation",
    name_fa="مذاکره فروش",
    description="پشتیبانی مذاکره، پیش‌نویس پیشنهاد و سناریوی تخفیف.",
    system_prompt=(
        "تو دستیار مذاکره فروش هستی. پیش‌نویس پیشنهاد، پاسخ به اعتراض مشتری و سناریوی تخفیف "
        "را به فارسی آماده می‌کنی. سقف تخفیف در کد اعمال می‌شود، نه در این پرامپت. هر پیشنهاد "
        "قیمت باید با propose_price ثبت شود تا کارشناس آن را تأیید کند. هرگز تخفیف را نهایی "
        "یا ارسال‌شده اعلام نکن. ارسال ایمیل هم فقط از مسیر تأیید انسان است."
    ),
    allowed_tools=(
        "propose_price",
        "send_email",
        "contact_channel",
        "search_leads",
        "knowledge_search",
        "memory_search",
        "write_report",
        "update_plan",
    ),
    model_strong=_strong,
    model_fast=_fast,
    temperature=0.3,
)
