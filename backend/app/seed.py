from __future__ import annotations

import logging
import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import settings
from app.database import open_session
from app.llm_defaults import apply_default_models
from app.models import Agent, Company, Contact, Deal, Lead, ToolRecord, User
from app.utils import utcnow

logger = logging.getLogger(__name__)


def seed_if_needed() -> None:
    if os.getenv("SKIP_STARTUP_SEED") == "1":
        return
    db = open_session()
    try:
        db.execute(text("SELECT 1"))
        seed_core(db)
        db.commit()
        logger.info("seed complete")
    except Exception:
        db.rollback()
        logger.exception("seed skipped because the database is not ready")
    finally:
        db.close()


def seed_core(db: Session) -> None:
    import app.agents.catalog  # noqa: F401
    import app.tools.builtin  # noqa: F401
    from app.agents.registry import registry
    from app.tools.base import tool_registry

    _seed_admin(db)
    _seed_demo_users(db)
    _seed_tools(db, tool_registry)
    _seed_channel_policies(db)
    _seed_agents(db, registry)
    _seed_samples(db)


def _seed_admin(db: Session) -> None:
    email = settings.admin_email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        return
    db.add(
        User(
            email=email,
            hashed_password=hash_password(settings.admin_password),
            full_name=settings.admin_name,
            role="admin",
            is_active=True,
        )
    )
    db.flush()


def _seed_demo_users(db: Session) -> None:
    rows = (
        (settings.sales_email, settings.sales_password, settings.sales_name, "sales"),
        (
            settings.supplier_email,
            settings.supplier_password,
            settings.supplier_name,
            "supplier_acquisition",
        ),
    )
    for email, password, name, role in rows:
        normalized = email.strip().lower()
        if not normalized or db.scalar(select(User).where(User.email == normalized)):
            continue
        db.add(
            User(
                email=normalized,
                hashed_password=hash_password(password),
                full_name=name,
                role=role,
                is_active=True,
            )
        )
    db.flush()


def _seed_channel_policies(db: Session) -> None:
    from app.models import ChannelPolicy

    for channel in ("email", "telegram", "whatsapp", "sms"):
        exists = db.scalar(
            select(ChannelPolicy).where(
                ChannelPolicy.channel == channel, ChannelPolicy.agent_id.is_(None)
            )
        )
        if exists is not None:
            continue
        db.add(
            ChannelPolicy(
                channel=channel,
                agent_id=None,
                mode="approval",
                daily_limit=settings.channel_daily_limit,
            )
        )
    db.flush()


def _seed_tools(db: Session, tool_registry) -> None:
    for tool in tool_registry.list():
        if db.scalar(select(ToolRecord).where(ToolRecord.name == tool.name)):
            continue
        db.add(
            ToolRecord(
                name=tool.name,
                description=tool.description,
                kind=tool.kind,
                input_schema=tool.input_schema,
                provider=tool.provider,
                is_enabled=True,
            )
        )
    db.flush()


def _seed_agents(db: Session, registry) -> None:
    """Insert missing plugins and refresh rows that still use automatic models.

    The resolved strong/fast pair follows the configured provider key. An
    admin's custom model (`model_*_is_default` is False) is not replaced.
    Rows seeded before that flag existed are updated only when they still
    hold a shipped default whose provider key is missing.
    """
    strong, fast = settings.resolved_model_defaults()
    anthropic = bool(settings.anthropic_api_key.strip())
    openai = bool(settings.openai_api_key.strip())
    gemini = bool(settings.gemini_api_key.strip())
    known = {spec.slug for spec in registry.list()}
    rows = {row.slug: row for row in db.scalars(select(Agent)).all()}
    for spec in registry.list():
        row = rows.get(spec.slug)
        if row is None:
            db.add(
                Agent(
                    slug=spec.slug,
                    name=spec.name,
                    name_fa=spec.name_fa,
                    description=spec.description,
                    system_prompt=spec.system_prompt,
                    allowed_tools=list(spec.allowed_tools),
                    model_strong=strong,
                    model_fast=fast,
                    model_strong_is_default=True,
                    model_fast_is_default=True,
                    temperature=spec.temperature,
                    is_active=True,
                    source="builtin",
                    config={},
                )
            )
            continue
        if apply_default_models(
            row,
            strong=strong,
            fast=fast,
            anthropic=anthropic,
            openai=openai,
            gemini=gemini,
        ):
            row.updated_at = utcnow()
        _sync_builtin_tools(row, spec)
    for slug, row in rows.items():
        if slug in known:
            continue
        if apply_default_models(
            row,
            strong=strong,
            fast=fast,
            anthropic=anthropic,
            openai=openai,
            gemini=gemini,
        ):
            row.updated_at = utcnow()
    db.flush()


_PREVIOUS_TOOLS = {
    "research": ["web_search", "web_fetch", "knowledge_search"],
    "lead_generation": ["web_search", "web_fetch", "crm_lookup", "send_email"],
    "sales_negotiation": ["propose_price", "crm_lookup", "send_email", "knowledge_search"],
    "consulting": ["web_search", "web_fetch", "knowledge_search"],
}


def _sync_builtin_tools(row: Agent, spec) -> None:
    config = dict(row.config or {})
    version = int(config.get("tools_version") or 1)
    if version >= 4:
        return
    current = list(row.allowed_tools or [])
    if version < 2:
        previous = _PREVIOUS_TOOLS.get(row.slug)
        if previous is not None and current == previous:
            current = list(spec.allowed_tools)
    if "update_plan" not in current:
        current.append("update_plan")
    extras = {
        "lead_generation": ["linkedin_search", "facebook_search", "contact_channel"],
        "sales_negotiation": ["contact_channel"],
        "research": ["linkedin_search", "facebook_search"],
        "consulting": ["linkedin_search"],
    }
    for name in extras.get(row.slug, []):
        if name not in current:
            current.append(name)
    row.allowed_tools = current
    config["tools_version"] = 4
    row.config = config
    row.updated_at = utcnow()


def _seed_samples(db: Session) -> None:
    if db.scalar(select(Company.id).limit(1)):
        return
    steel = Company(
        name="فولاد البرز",
        industry="فلزات",
        website="https://example.com/alborz-steel",
        city="تهران",
        notes="دادهٔ نمونه برای محیط توسعه.",
    )
    pack = Company(
        name="صنایع بسته‌بندی کاسپین",
        industry="بسته‌بندی",
        website="https://example.com/caspian-pack",
        city="رشت",
        notes="دادهٔ نمونه.",
    )
    textile = Company(
        name="نساجی پارس‌ریس",
        industry="نساجی",
        website="https://example.com/parsriss",
        city="اصفهان",
        notes="دادهٔ نمونه.",
    )
    db.add_all([steel, pack, textile])
    db.flush()

    lead_steel = Lead(
        company_id=steel.id,
        title="تأمین ورق برای خط جدید",
        source="نمایشگاه",
        party="supplier",
        status="negotiating",
        score=78,
        notes="علاقه‌مند به قرارداد فصلی.",
    )
    lead_pack = Lead(
        company_id=pack.id,
        title="جعبه‌های صادراتی مواد غذایی",
        source="معرفی",
        party="customer",
        status="qualified",
        score=64,
        notes="نیاز به نمونه در اندازهٔ صادراتی.",
    )
    lead_textile = Lead(
        company_id=textile.id,
        title="پارچهٔ فنی برای لباس کار",
        source="وب",
        party="supplier",
        status="new",
        score=41,
        notes="هنوز تماس اول انجام نشده.",
    )
    db.add_all([lead_steel, lead_pack, lead_textile])
    db.flush()
    db.add_all(
        [
            Contact(
                company_id=steel.id,
                lead_id=lead_steel.id,
                name="رضا مرادی",
                email="reza@example.com",
                phone="021-00000000",
                title="مدیر خرید",
                party="supplier",
            ),
            Contact(
                company_id=pack.id,
                lead_id=lead_pack.id,
                name="نسترن کیانی",
                email="nastaran@example.com",
                phone="013-00000000",
                title="کارشناس توسعه محصول",
                party="customer",
            ),
            Deal(
                lead_id=lead_steel.id,
                title="پیش‌فاکتور ورق سه ماهه",
                value=18500000000,
                currency="IRR",
                stage="quoted",
                discount_percent=8,
            ),
        ]
    )
    db.flush()
