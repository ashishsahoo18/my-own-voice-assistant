"""Data models and enums for OLIVER 2.0 Productivity Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class TaskItem:
    """Represents a tracked user task or to-do item."""

    id: int
    title: str
    description: str = ""
    due_date: Optional[str] = None
    priority: str = TaskPriority.NORMAL.value
    status: str = TaskStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    completed_at: Optional[str] = None
    metadata_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "due_date": self.due_date,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "metadata_json": self.metadata_json,
        }


class ReminderStatus(str, Enum):
    PENDING = "pending"
    DUE = "due"
    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    MISSED = "missed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    DISPATCH_FAILED = "dispatch_failed"


class RecurrenceType(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class ReminderItem:
    """Represents a scheduled reminder in the unified database."""

    id: int
    title: str
    remind_at: str
    created_at: str
    completed: int = 0
    recurrence: str = RecurrenceType.NONE.value
    priority: str = "normal"
    status: str = ReminderStatus.PENDING.value
    lease_until: Optional[str] = None
    claimed_by: Optional[str] = None
    dispatched_at: Optional[str] = None
    delivery_channels: str = "[]"
    dispatch_attempts: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "remind_at": self.remind_at,
            "created_at": self.created_at,
            "completed": self.completed,
            "recurrence": self.recurrence,
            "priority": self.priority,
            "status": self.status,
            "lease_until": self.lease_until,
            "claimed_by": self.claimed_by,
            "dispatched_at": self.dispatched_at,
            "delivery_channels": self.delivery_channels,
            "dispatch_attempts": self.dispatch_attempts,
            "last_error": self.last_error,
        }


@dataclass
class NoteItem:
    """Represents a user note with full-text search capability."""

    id: int
    title: str
    content: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DailyPlan:
    """Aggregated daily planner briefing data."""

    date: str
    tasks_due: list[TaskItem] = field(default_factory=list)
    reminders_due: list[ReminderItem] = field(default_factory=list)
    overdue_tasks: list[TaskItem] = field(default_factory=list)
    overdue_reminders: list[ReminderItem] = field(default_factory=list)
    summary_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "tasks_due": [t.to_dict() for t in self.tasks_due],
            "reminders_due": [r.to_dict() for r in self.reminders_due],
            "overdue_tasks": [t.to_dict() for t in self.overdue_tasks],
            "overdue_reminders": [r.to_dict() for r in self.overdue_reminders],
            "summary_text": self.summary_text,
        }
