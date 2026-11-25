from app.agents.registry import AgentSpec
from app.config import settings
from app.tools.browser_agent import BROWSER_TOOL_NAMES

_strong, _fast = settings.resolved_model_defaults()

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
    allowed_tools=(
        "web_search",
        "web_fetch",
        "browser",
        "create_lead",
        "update_lead",
        "search_leads",
        "export_leads",
        "send_email",
        "linkedin_search",
        "facebook_search",
        "contact_channel",
        "memory_save",
        "memory_search",
        "remember",
        "recall",
        "update_plan",
    )
    + BROWSER_TOOL_NAMES,
    model_strong=_strong,
    model_fast=_fast,
    temperature=0.4,
)
