from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    source: str
    category: str
    value: float
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None


class EventOut(BaseModel):
    id: int
    source: str
    category: str
    value: float
    occurred_at: datetime
    metadata: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class AgentChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreateRequest(BaseModel):
    username: str
    password: str
    roles: list[str] = Field(default_factory=list)
    tenant_id: str | None = None


class TenantCreateRequest(BaseModel):
    name: str


class TenantUpdateRequest(BaseModel):
    is_active: bool


class PermissionCreateRequest(BaseModel):
    name: str
    description: str = ""


class RolePermissionRequest(BaseModel):
    role: str
    permissions: list[str]


class AuditQuery(BaseModel):
    action: str | None = None
    target: str | None = None
    user_id: int | None = None
    request_id: str | None = None
    limit: int = 100


class ReportJobCreate(BaseModel):
    name: str
    schedule: str = "daily"
    format: str = "csv"
    group_by: str = "category"
    metric: str = "value"
    agg: str = "sum"
    tenant_id: str | None = None


class AgentChatResponse(BaseModel):
    answer: str
    data: list[dict[str, Any]]
    sql: str | None = None
