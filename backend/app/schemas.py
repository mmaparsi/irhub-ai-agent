from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: Literal["admin", "expert", "viewer"] = "expert"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Literal["admin", "expert", "viewer"] | None = None
    is_active: bool | None = None


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    name_fa: str
    description: str
    system_prompt: str
    allowed_tools: list[str]
    model_strong: str
    model_fast: str
    model_strong_is_default: bool | None = None
    model_fast_is_default: bool | None = None
    temperature: float
    is_active: bool
    source: str
    created_at: datetime
    updated_at: datetime


class AgentCreate(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=255)
    name_fa: str = Field(min_length=1, max_length=255)
    description: str = ""
    system_prompt: str = Field(min_length=1)
    allowed_tools: list[str] = []
    model_strong: str = Field(min_length=1, max_length=255)
    model_fast: str = Field(min_length=1, max_length=255)
    temperature: float = Field(default=0.3, ge=0, le=2)
    is_active: bool = True


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    name_fa: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    allowed_tools: list[str] | None = None
    model_strong: str | None = Field(default=None, min_length=1, max_length=255)
    model_fast: str | None = Field(default=None, min_length=1, max_length=255)
    temperature: float | None = Field(default=None, ge=0, le=2)
    is_active: bool | None = None


class ToolOut(BaseModel):
    name: str
    description: str
    kind: str
    provider: str
    is_enabled: bool
    input_schema: dict[str, Any]


class ConversationIn(BaseModel):
    agent_id: str | None = None
    title: str = ""


class ConversationOut(BaseModel):
    id: str
    title: str
    status: str
    agent_id: str | None
    agent_name: str | None
    created_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    seq: int
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    tier: Literal["strong", "fast"] = "strong"


class TaskIn(BaseModel):
    task: str = Field(min_length=1, max_length=8000)
    agent_slug: str | None = None
    tier: Literal["strong", "fast"] = "strong"


class TaskOut(BaseModel):
    conversation_id: str
    agent_slug: str
    result: str
    approval_ids: list[str]


class ApprovalIn(BaseModel):
    action_type: Literal["email", "message", "price_offer"]
    payload: dict[str, Any]
    conversation_id: str | None = None
    agent_id: str | None = None


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = ""


class ApprovalOut(BaseModel):
    id: str
    action_type: str
    payload: dict[str, Any]
    status: str
    execution_status: str
    decision_note: str
    rule_snapshot: dict[str, Any]
    created_at: datetime
    decided_at: datetime | None
    executed_at: datetime | None
    requested_by_name: str | None
    agent_name: str | None


class ContactOut(BaseModel):
    name: str
    email: str
    phone: str
    title: str


class DealOut(BaseModel):
    title: str
    value: float
    currency: str
    stage: str
    discount_percent: float


class LeadOut(BaseModel):
    id: str
    title: str
    source: str
    status: str
    score: int
    notes: str
    company_name: str
    city: str
    industry: str
    contacts: list[ContactOut]
    deals: list[DealOut]
    created_at: datetime


class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source: str = ""


class KnowledgeOut(BaseModel):
    id: str
    title: str
    source: str
    status: str
    excerpt: str
    created_at: datetime


class DashboardOut(BaseModel):
    agents: int
    pending_approvals: int
    leads: int
    documents: int
    mock_llm: bool
    max_discount_percent: float
