from app.agents.registry import AgentSpec
from app.config import settings

_strong, _fast = settings.resolved_model_defaults()

SPEC = AgentSpec(
    slug="supervisor",
    name="Supervisor",
    name_fa="سرپرست",
    description="هدف را بین عامل‌های متخصص تقسیم می‌کند و گزارش‌ها را جمع می‌کند.",
    system_prompt=(
        "تو سرپرست عامل‌های ایرهاب هستی. هدف کاربر را به زیرهدف‌های مشخص بشکن و با ابزار delegate "
        "به research، lead_generation، sales_negotiation یا consulting بسپار. "
        "نتیجه‌ها را به فارسی جمع کن و داده را جعل نکن."
    ),
    allowed_tools=("delegate", "memory_search", "write_report"),
    model_strong=_strong,
    model_fast=_fast,
    temperature=0.2,
)
