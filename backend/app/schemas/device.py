"""Device registry schemas."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    device_name: str = Field(min_length=1, max_length=100)
    device_type: str = Field(default="desktop", description="desktop, mobile, or web")
    platform: str = Field(default="windows", description="windows, android, ios, macos, linux")
    client_version: str = Field(default="3.0.0")


class DeviceResponse(BaseModel):
    id: str
    device_name: str
    device_type: str
    platform: str
    client_version: str
    registered_at: datetime
    last_active_at: datetime

