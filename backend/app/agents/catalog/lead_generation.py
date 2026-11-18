from app.agents.registry import AgentSpec
from app.config import settings

SPEC = AgentSpec(
    slug="lead_generation",
    name="Lead Generation",
    name_fa="مشتری‌یابی",
    description="پیدا کردن و اولویت‌بندی مشتریان بالقوهٔ صنعتی.",
    system_prompt=(
        "تو عامل مشتری‌یابی هستی. به کارشناسان کمک می‌کنی سرنخ‌های صنعتی را پیدا و "
        "اولویت‌بندی کنند. خروجی را به فارسی و در قالب فهرست، با دلیل کوتاه برای هر سرنخ بنویس. "
        "از crm_lookup برای داده‌های موجود و از web_search برای نشانه‌های عمومی استفاده کن. "
        "هیچ پیامی را مستقیم برای مشتری ارسال نکن؛ ارسال فقط پس از تأیید انسان انجام می‌شود "
        "و ابزار send_email فقط یک درخواست تأیید می‌سازد."
    ),
    allowed_tools=("web_search", "web_fetch", "crm_lookup", "send_email"),
    model_strong=settings.model_strong_default,
    model_fast=settings.model_fast_default,
    temperature=0.4,
)
