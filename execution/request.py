"""Structured TaskRequest definition for central execution pipeline."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class TaskRequest(BaseModel):
    """Authoritative task request for executing actions in OLIVER 2.0."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = Field(description="Unique tool identifier, e.g. 'files.create_file'")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Validated tool arguments")
    risk_level: Optional[int] = Field(default=None, description="Explicit risk level if pre-evaluated")
    confirmation_token: Optional[str] = Field(default=None, description="Action-bound confirmation token")
    user_confirmed: bool = Field(default=False, description="True if human confirmation was obtained")
    timeout_s: float = Field(default=15.0, ge=0.01, le=120.0, description="Execution timeout limit")
    created_at: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Caller context metadata")

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("tool_name cannot be empty")
        if "." not in cleaned and cleaned != "custom":
            raise ValueError(f"tool_name must follow 'skill.tool' convention, got '{v}'")
        return cleaned

    def validate_integrity(self) -> tuple[bool, str]:
        """Validate request completeness before execution."""
        if not self.tool_name:
            return False, "Missing tool_name."
        if not isinstance(self.arguments, dict):
            return False, "Arguments must be a dictionary."
        if self.timeout_s <= 0:
            return False, "Timeout must be greater than zero."
        return True, ""
