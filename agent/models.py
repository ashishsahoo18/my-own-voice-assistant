"""Data models for multi-step agent planning and execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class PlanStep:
    """A single atomic action in a multi-step task plan."""

    step_number: int
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    requires_confirmation: bool = False
    expected_outcome: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "description": self.description,
            "requires_confirmation": self.requires_confirmation,
            "expected_outcome": self.expected_outcome,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        return cls(
            step_number=int(data.get("step_number", 1)),
            tool_name=str(data.get("tool_name", "")),
            arguments=dict(data.get("arguments", {})),
            description=str(data.get("description", "")),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            expected_outcome=str(data.get("expected_outcome", "")),
        )


@dataclass
class Plan:
    """A validated, bounded sequence of steps designed to achieve a goal."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    plan_id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED, REPLANNING
    current_step_index: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    replan_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "current_step_index": self.current_step_index,
            "created_at": self.created_at,
            "replan_count": self.replan_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        return cls(
            goal=str(data.get("goal", "")),
            steps=[PlanStep.from_dict(s) for s in data.get("steps", [])],
            plan_id=str(data.get("plan_id", f"plan_{uuid.uuid4().hex[:12]}")),
            status=str(data.get("status", "PENDING")),
            current_step_index=int(data.get("current_step_index", 0)),
            created_at=str(data.get("created_at", datetime.now().isoformat())),
            replan_count=int(data.get("replan_count", 0)),
        )


@dataclass
class StepResult:
    """Outcome and observable verification details for an executed step."""

    step_number: int
    tool_name: str
    status: str  # SUCCESS, FAILED, DENIED, CANCELLED, UNVERIFIED, TIMEOUT
    message: str
    verification_status: str  # VERIFIED, UNVERIFIED, FAILED
    verification_evidence: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "tool_name": self.tool_name,
            "status": self.status,
            "message": self.message,
            "verification_status": self.verification_status,
            "verification_evidence": self.verification_evidence,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class TaskReport:
    """Honest post-execution report summarizing multi-step task execution."""

    task_id: str
    goal: str
    overall_status: str  # SUCCESS, FAILED, CANCELLED, REPLAN_EXHAUSTED, PARTIAL
    steps_executed: list[StepResult] = field(default_factory=list)
    summary: str = ""
    total_duration_seconds: float = 0.0
    replan_count: int = 0

    @property
    def is_success(self) -> bool:
        return self.overall_status == "SUCCESS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "overall_status": self.overall_status,
            "steps_executed": [s.to_dict() for s in self.steps_executed],
            "summary": self.summary,
            "total_duration_seconds": self.total_duration_seconds,
            "replan_count": self.replan_count,
        }
