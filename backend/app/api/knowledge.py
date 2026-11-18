from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.deps import get_current_user, require_roles
from app.database import get_db
from app.knowledge.embeddings import embed_text
from app.knowledge.search import search_documents
from app.models import KnowledgeDocument, User
from app.schemas import KnowledgeIn, KnowledgeOut
from app.worker.queue import enqueue

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _out(row: KnowledgeDocument) -> KnowledgeOut:
    excerpt = row.content[:240].replace("\n", " ")
    return KnowledgeOut(
        id=row.id,
        title=row.title,
        source=row.source,
        status=row.status,
        excerpt=excerpt,
        created_at=row.created_at,
    )


@router.get("", response_model=list[KnowledgeOut])
def list_documents(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[KnowledgeOut]:
    rows = db.scalars(
        select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()).limit(100)
    ).all()
    return [_out(row) for row in rows]


@router.post("", response_model=KnowledgeOut, status_code=201)
async def create_document(
    body: KnowledgeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "expert")),
) -> KnowledgeOut:
    document = KnowledgeDocument(
        title=body.title.strip(),
        content=body.content.strip(),
        source=(body.source or "upload").strip() or "upload",
        status="ready",
        embedding=embed_text(f"{body.title}\n{body.content}"),
        meta={},
        uploaded_by=user.id,
    )
    db.add(document)
    db.flush()
    write_audit(
        db,
        actor_id=user.id,
        action="knowledge.upload",
        entity_type="knowledge_document",
        entity_id=document.id,
        details={"title": document.title},
    )
    db.commit()
    db.refresh(document)
    await enqueue("index_document", document.id)
    return _out(document)


@router.get("/search", response_model=list[KnowledgeOut])
def search(
    q: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[KnowledgeOut]:
    found = search_documents(db, q, limit=8)
    return [_out(row) for row, _distance in found]
