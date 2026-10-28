"""Skill, Tool, and Plugin base contracts for OLIVER 2.0."""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Callable, Optional
from pydantic import BaseModel, Field


class ToolRiskLevel(IntEnum):
    """Risk levels for tool execution per Section 4.2."""

    SAFE = 0        # Answering questions, reading info, harmless websites
    LOW = 1         # Creating notes, opening applications, non-sensitive files
    SENSITIVE = 2   # Sending messages/emails, account actions, modifying important files
    DANGEROUS = 3   # Deleting files, shutdown/restart, system changes, credentials


class ToolResult(BaseModel):
    """Standardized typed result returned by every tool execution."""

    status: str = Field(
        default="SUCCESS",
        description="One of: SUCCESS, VERIFIED, UNVERIFIED, FAILED, DENIED, CANCELLED, TIMEOUT",
    )
    message: str = Field(default="", description="User-facing summary message")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured output payload")
    evidence: dict[str, Any] = Field(default_factory=dict, description="Verification evidence")
    error: Optional[str] = Field(default=None, description="Error message if failed")

    @property
    def is_success(self) -> bool:
        return self.status in {"SUCCESS", "VERIFIED"}


class ToolSpec(BaseModel):
    """Specification and schema for an individual skill tool."""

    name: str = Field(description="Unique tool identifier, e.g. 'windows.open_app'")
    description: str = Field(description="One-line human/LLM description of tool capability")
    risk_level: ToolRiskLevel = Field(default=ToolRiskLevel.SAFE)
    requires_confirmation: bool = Field(default=False)
    timeout_s: float = Field(default=15.0, ge=1.0, le=120.0)
    idempotent: bool = Field(default=False)
    handler: Optional[Callable[..., Any]] = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True


class SkillManifest(BaseModel):
    """Metadata manifest declaring a skill's capabilities and dependencies."""

    name: str = Field(description="Skill name, e.g. 'windows'")
    version: str = Field(default="1.0.0")
    description: str = Field(description="Human-readable description of the skill")
    triggers: list[str] = Field(default_factory=list, description="Example natural-language triggers")
    required_permissions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list, description="Required packages or binaries")
    enabled_by_default: bool = Field(default=True)


class BaseSkill:
    """Abstract base class that all OLIVER skills implement."""

    def __init__(self) -> None:
        self.enabled: bool = True

    def get_manifest(self) -> SkillManifest:
        """Return the skill's declarative manifest."""
        raise NotImplementedError

    def get_tools(self) -> list[ToolSpec]:
        """Return list of executable tool specifications provided by this skill."""
        raise NotImplementedError

    def health_check(self) -> tuple[bool, str]:
        """Verify dependencies and readiness. Returns (is_healthy, status_message)."""
        return True, "Ready"
