from app.agents.registry import AgentSpec
from app.config import settings
from app.tools.browser_agent import BROWSER_TOOL_NAMES

_strong, _fast = settings.resolved_model_defaults()

SPEC = AgentSpec(
    slug="research",
    name="Market Research",
    name_fa="تحقیق بازار",
    description="پژوهش بازار، رقبا و روندها برای تولیدکنندگان.",
    system_prompt=(
        "تو عامل تحقیق بازار «ایرهاب» هستی. با کارشناسان یک شرکت تولیدی به فارسی "
        "گفتگو می‌کنی، مگر اینکه کاربر زبان دیگری بخواهد. پاسخ را مختصر، ساخت‌یافته "
        "و قابل اقدام بنویس. برای دادهٔ زنده از web_search و web_fetch استفاده کن و "
        "آمار را جعل نکن. اگر نمی‌دانی، شفاف بگو. برای دانش داخلی از knowledge_search استفاده کن."
    ),
    allowed_tools=(
        "web_search",
        "web_fetch",
        "linkedin_search",
        "facebook_search",
        "browser",
        "knowledge_search",
        "memory_save",
        "memory_search",
        "remember",
        "recall",
        "python_exec",
        "write_report",
        "update_plan",
    )
    + BROWSER_TOOL_NAMES,
    model_strong=_strong,
    model_fast=_fast,
    temperature=0.2,
)
