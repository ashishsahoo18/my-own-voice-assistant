"""Chat and conversation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="User prompt or command")
    conversation_id: Optional[str] = Field(default=None, description="Existing conversation ID or None for auto-create")
    request_id: Optional[str] = Field(default=None, description="Client-generated idempotency request UUIDv4")


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    latency_ms: float
    model: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    latency_ms: Optional[float] = None
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]

