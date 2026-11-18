from app.agents.registry import AgentSpec
from app.config import settings

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
    allowed_tools=("web_search", "web_fetch", "knowledge_search"),
    model_strong=settings.model_strong_default,
    model_fast=settings.model_fast_default,
    temperature=0.4,
)
