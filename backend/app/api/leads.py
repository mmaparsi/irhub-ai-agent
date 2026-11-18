from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models import Company, Contact, Deal, Lead, User
from app.schemas import ContactOut, DealOut, LeadOut

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=list[LeadOut])
def list_leads(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[LeadOut]:
    leads = db.scalars(select(Lead).order_by(Lead.created_at.desc())).all()
    company_ids = {item.company_id for item in leads if item.company_id}
    lead_ids = [item.id for item in leads]
    companies = {}
    if company_ids:
        companies = {
            row.id: row
            for row in db.scalars(select(Company).where(Company.id.in_(company_ids))).all()
        }
    contacts: dict[str, list[Contact]] = {}
    deals: dict[str, list[Deal]] = {}
    if lead_ids:
        for contact in db.scalars(select(Contact).where(Contact.lead_id.in_(lead_ids))).all():
            contacts.setdefault(contact.lead_id or "", []).append(contact)
        for deal in db.scalars(select(Deal).where(Deal.lead_id.in_(lead_ids))).all():
            deals.setdefault(deal.lead_id or "", []).append(deal)
    result: list[LeadOut] = []
    for lead in leads:
        company = companies.get(lead.company_id or "")
        result.append(
            LeadOut(
                id=lead.id,
                title=lead.title,
                source=lead.source,
                status=lead.status,
                score=lead.score,
                notes=lead.notes,
                company_name=company.name if company else "",
                city=company.city if company else "",
                industry=company.industry if company else "",
                contacts=[
                    ContactOut(name=item.name, email=item.email, phone=item.phone, title=item.title)
                    for item in contacts.get(lead.id, [])
                ],
                deals=[
                    DealOut(
                        title=item.title,
                        value=float(item.value or 0),
                        currency=item.currency,
                        stage=item.stage,
                        discount_percent=float(item.discount_percent or 0),
                    )
                    for item in deals.get(lead.id, [])
                ],
                created_at=lead.created_at,
            )
        )
    return result
