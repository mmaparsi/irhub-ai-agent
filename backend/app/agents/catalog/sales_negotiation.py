from app.agents.registry import AgentSpec
from app.config import settings

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
    allowed_tools=("propose_price", "crm_lookup", "send_email", "knowledge_search"),
    model_strong=settings.model_strong_default,
    model_fast=settings.model_fast_default,
    temperature=0.3,
)
