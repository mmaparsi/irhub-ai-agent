from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.embeddings import embed_text
from app.models import KnowledgeDocument


def search_documents(
    db: Session, query: str, limit: int = 5
) -> list[tuple[KnowledgeDocument, float | None]]:
    if db.bind is not None and db.bind.dialect.name != "postgresql":
        rows = db.scalars(select(KnowledgeDocument).limit(limit)).all()
        return [(row, None) for row in rows]

    vector = embed_text(query)
    distance = KnowledgeDocument.embedding.cosine_distance(vector)
    stmt = (
        select(KnowledgeDocument, distance.label("distance"))
        .where(KnowledgeDocument.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return [(row, dist) for row, dist in db.execute(stmt).all()]
