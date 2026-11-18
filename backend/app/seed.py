from __future__ import annotations

import logging
import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import settings
from app.database import open_session
from app.models import Agent, Company, Contact, Deal, Lead, ToolRecord, User

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
    _seed_tools(db, tool_registry)
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
    for spec in registry.list():
        if db.scalar(select(Agent).where(Agent.slug == spec.slug)):
            continue
        db.add(
            Agent(
                slug=spec.slug,
                name=spec.name,
                name_fa=spec.name_fa,
                description=spec.description,
                system_prompt=spec.system_prompt,
                allowed_tools=list(spec.allowed_tools),
                model_strong=spec.model_strong,
                model_fast=spec.model_fast,
                temperature=spec.temperature,
                is_active=True,
                source="builtin",
                config={},
            )
        )
    db.flush()


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
        status="negotiating",
        score=78,
        notes="علاقه‌مند به قرارداد فصلی.",
    )
    lead_pack = Lead(
        company_id=pack.id,
        title="جعبه‌های صادراتی مواد غذایی",
        source="معرفی",
        status="qualified",
        score=64,
        notes="نیاز به نمونه در اندازهٔ صادراتی.",
    )
    lead_textile = Lead(
        company_id=textile.id,
        title="پارچهٔ فنی برای لباس کار",
        source="وب",
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
            ),
            Contact(
                company_id=pack.id,
                lead_id=lead_pack.id,
                name="نسترن کیانی",
                email="nastaran@example.com",
                phone="013-00000000",
                title="کارشناس توسعه محصول",
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
