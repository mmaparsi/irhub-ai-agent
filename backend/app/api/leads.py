from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_staff
from app.auth.rbac import lead_visible
from app.database import get_db
from app.models import Company, Contact, Deal, Lead, User
from app.schemas import ContactOut, DealOut, LeadOut

router = APIRouter(prefix="/leads", tags=["leads"])


def _visible_leads(db: Session, user: User) -> list[Lead]:
    rows = db.scalars(select(Lead).order_by(Lead.created_at.desc())).all()
    return [row for row in rows if lead_visible(user, row)]


def _one(db: Session, lead: Lead) -> LeadOut:
    company = db.get(Company, lead.company_id) if lead.company_id else None
    contacts = db.scalars(select(Contact).where(Contact.lead_id == lead.id)).all()
    deals = db.scalars(select(Deal).where(Deal.lead_id == lead.id)).all()
    return LeadOut(
        id=lead.id,
        title=lead.title,
        source=lead.source,
        status=lead.status,
        score=lead.score,
        notes=lead.notes,
        company_name=company.name if company else "",
        city=company.city if company else "",
        industry=company.industry if company else "",
        website=company.website if company else "",
        party=lead.party or "customer",
        contacts=[
            ContactOut(name=item.name, email=item.email, phone=item.phone, title=item.title)
            for item in contacts
        ],
        deals=[
            DealOut(
                title=item.title,
                value=float(item.value or 0),
                currency=item.currency,
                stage=item.stage,
                discount_percent=float(item.discount_percent or 0),
            )
            for item in deals
        ],
        created_at=lead.created_at,
    )


@router.get("/export.csv")
def export_leads(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> Response:
    from app.models import Company, Contact

    leads = _visible_leads(db, user)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "company",
            "city",
            "party",
            "title",
            "status",
            "score",
            "contact",
            "email",
            "phone",
            "notes",
        ]
    )
    for lead in leads:
        company = db.get(Company, lead.company_id) if lead.company_id else None
        contact = db.scalar(select(Contact).where(Contact.lead_id == lead.id))
        writer.writerow(
            [
                company.name if company else "",
                company.city if company else "",
                lead.party,
                lead.title,
                lead.status,
                lead.score,
                contact.name if contact else "",
                contact.email if contact else "",
                contact.phone if contact else "",
                lead.notes,
            ]
        )
    return Response(
        "\ufeff" + buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@router.get("", response_model=list[LeadOut])
def list_leads(
    party: str | None = None,
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> list[LeadOut]:
    rows = _visible_leads(db, user)
    needle = (q or "").strip().casefold()
    result: list[LeadOut] = []
    for lead in rows:
        if party and lead.party != party:
            continue
        if status and lead.status != status:
            continue
        if source and source.casefold() not in (lead.source or "").casefold():
            continue
        item = _one(db, lead)
        if (
            needle
            and needle
            not in " ".join(
                [item.title, item.company_name, item.city, item.notes, item.source]
            ).casefold()
        ):
            continue
        result.append(item)
    return result


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
) -> LeadOut:
    lead = db.get(Lead, lead_id)
    if lead is None or not lead_visible(user, lead):
        raise HTTPException(status_code=404, detail="سرنخ پیدا نشد")
    return _one(db, lead)
