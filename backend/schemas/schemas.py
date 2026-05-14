"""Pydantic v2 schemas for request / response payloads."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ------------------- auth -------------------
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(default="analyst", pattern="^(admin|analyst|viewer)$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ------------------- events -------------------
class EventIn(BaseModel):
    source: str
    event_type: str
    src_ip: Optional[str] = None
    dst_ip: Optional[str] = None
    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    protocol: Optional[str] = None
    severity: float = 0.5
    description: str = ""
    raw: dict[str, Any] = {}


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source: str
    event_type: str
    src_ip: Optional[str]
    dst_ip: Optional[str]
    severity: float
    description: str
    enrichment: dict[str, Any]
    timestamp: datetime
    incident_id: Optional[uuid.UUID] = None


# ------------------- incidents -------------------
class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    status: str
    severity: float
    risk_score: float
    explanation: str
    recommended_actions: list[str] | list[dict] = []
    tactics: list[str] = []
    created_at: datetime
    updated_at: datetime


class IncidentDetail(IncidentOut):
    events: list[EventOut] = []


# ------------------- feedback -------------------
class FeedbackIn(BaseModel):
    verdict: str = Field(pattern="^(confirmed|false_positive|dismissed)$")
    notes: str = ""


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    incident_id: uuid.UUID
    verdict: str
    notes: str
    created_at: datetime


# ------------------- graph -------------------
class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    properties: dict[str, Any] = {}


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ------------------- risk weights -------------------
class RiskWeightsIn(BaseModel):
    alpha: float = Field(ge=0, le=1)
    beta: float = Field(ge=0, le=1)
    gamma: float = Field(ge=0, le=1)


class RiskWeightsOut(RiskWeightsIn):
    updated_at: datetime
