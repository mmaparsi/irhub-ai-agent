from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.agents.catalog  # noqa: F401
import app.tools.builtin  # noqa: F401
from app.api.router import api
from app.config import settings
from app.database import get_db
from app.logging_config import configure_logging
from app.observability import configure_observability
from app.seed import seed_if_needed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    if settings.environment == "production" and settings.jwt_secret == "dev-only-change-me":
        raise RuntimeError("JWT_SECRET must be changed when ENVIRONMENT=production")
    configure_observability()
    import app.agents.catalog  # noqa: F401
    import app.tools.builtin  # noqa: F401

    seed_if_needed()
    yield


app = FastAPI(title="IRHub", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    db.execute(text("SELECT 1"))
    strong, fast = settings.resolved_model_defaults()
    return {
        "status": "ok",
        "mock_llm": settings.llm_is_mock(),
        "max_discount_percent": settings.max_discount_percent,
        "model_strong_default": strong,
        "model_fast_default": fast,
    }
