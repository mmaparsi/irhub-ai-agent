from fastapi import APIRouter

from app.api import agents, approvals, auth, chat, knowledge, leads, users

api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(users.router)
api.include_router(agents.router)
api.include_router(chat.router)
api.include_router(approvals.router)
api.include_router(leads.router)
api.include_router(knowledge.router)
