"""Common schemas: health, welcome, error structures."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "3.0.0"
    environment: str
    database: str
    ollama_status: str
    ollama_model: str


class WelcomeResponse(BaseModel):
    greeting: str
    user_name: str
    device_name: Optional[str] = None
    server_time: str
    quick_tips: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str

