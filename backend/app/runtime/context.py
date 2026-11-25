from __future__ import annotations

import contextvars
from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass
class RunContext:
    db: Session
    task_id: str
    user_id: str
    agent_id: str | None
    agent_slug: str
    thread_id: str
    saver: object
    depth: int = 0
    budget: int = 6


run_context: contextvars.ContextVar[RunContext] = contextvars.ContextVar("run_context")
