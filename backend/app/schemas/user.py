"""User profile and preference schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    id: str
    email: str = Field(pattern=r"^[\w\.\+\-]+@[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}$")
    full_name: str
    preferences: Dict[str, Any]
    is_active: bool
    created_at: datetime


class UpdatePreferencesRequest(BaseModel):
    preferences: Dict[str, Any]
