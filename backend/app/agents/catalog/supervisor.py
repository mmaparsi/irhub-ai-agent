from app.agents.registry import AgentSpec
from app.config import settings

_strong, _fast = settings.resolved_model_defaults()

SPEC = AgentSpec(
    slug="supervisor",
    name="Supervisor",
    name_fa="سرپرست",
    description="هدف را بین عامل‌های متخصص تقسیم می‌کند و گزارش‌ها را جمع می‌کند.",
    system_prompt=(
        "تو سرپرست عامل‌های ایرهاب هستی. هدف را به زیرهدف‌های مستقل بشکن. "
        "با delegate و در صورت نیاز آرایه jobs چند متخصص را در یک فراخوانی صدا بزن: "
        "research، lead_generation، sales_negotiation، consulting. "
        "فقط متخصص‌هایی که نقش کاربر اجازه می‌دهد. نتیجه‌ها را در یک گزارش فارسی جمع کن."
    ),
    allowed_tools=(
        "delegate",
        "memory_search",
        "remember",
        "recall",
        "write_report",
        "update_plan",
    ),
    model_strong=_strong,
    model_fast=_fast,
    temperature=0.2,
)
