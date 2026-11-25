from app.agents.registry import AgentSpec
from app.config import settings

_strong, _fast = settings.resolved_model_defaults()

SPEC = AgentSpec(
    slug="consulting",
    name="Design and Commercialization",
    name_fa="مشاوره طراحی و تجاری‌سازی",
    description="مشاوره طراحی محصول و مسیر تجاری‌سازی برای تولیدکنندگان.",
    system_prompt=(
        "تو مشاور طراحی و تجاری‌سازی محصول برای تولیدکنندگان هستی. از نیاز بازار تا بسته‌بندی "
        "پیشنهاد، گام‌های عملی، ریسک‌ها و سؤال‌های باز را به فارسی توضیح بده. ادعاهای بازار را "
        "از قضاوت طراحی جدا کن و اگر به داده نیاز داری از web_search یا knowledge_search استفاده کن."
    ),
    allowed_tools=(
        "web_search",
        "web_fetch",
        "linkedin_search",
        "knowledge_search",
        "python_exec",
        "memory_search",
        "remember",
        "recall",
        "write_report",
        "update_plan",
    ),
    model_strong=_strong,
    model_fast=_fast,
    temperature=0.4,
)
