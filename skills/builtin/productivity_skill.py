"""Productivity, tasks, reminders, notes, daily briefing, and safe math calculation skill for OLIVER 2.0."""

from __future__ import annotations

import ast
import operator
import re
from pathlib import Path
from typing import Any, Optional

from commands.productivity import ProductivityCommands
from productivity.datetime_parser import DateTimeParser
from productivity.models import RecurrenceType, TaskPriority, TaskStatus
from productivity.service import ProductivityService, get_productivity_service
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec

# Safe arithmetic operators mapping
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_math(expr: str) -> float | int:
    """Safely evaluate mathematical expressions using AST without eval()."""
    def _eval(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
            left = _eval(node.left)
            right = _eval(node.right)
            return SAFE_OPERATORS[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPERATORS:
            operand = _eval(node.operand)
            return SAFE_OPERATORS[type(node.op)](operand)
        raise ValueError(f"Unsupported math syntax: {ast.dump(node)}")

    tree = ast.parse(expr.strip(), mode="eval")
    return _eval(tree)


class ProductivitySkill(BaseSkill):
    """Adapter wrapping tasks, scheduled reminders, searchable notes, daily briefing, and math."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        service: Optional[ProductivityService] = None,
    ) -> None:
        super().__init__()
        if service is not None:
            self.service = service
        elif db_path is not None:
            from memory.unified_db import UnifiedDatabase
            custom_db = UnifiedDatabase(db_path=Path(db_path))
            self.service = ProductivityService(db=custom_db, start_scheduler=False)
        else:
            self.service = get_productivity_service()

        self.productivity = ProductivityCommands()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="productivity",
            version="2.0.0",
            description="Manage user tasks, scheduled reminders, searchable notes, daily briefing, and calculations.",
            triggers=[
                "calculate",
                "remind me",
                "show reminders",
                "list tasks",
                "add task",
                "save note",
                "search notes",
                "daily plan",
                "morning briefing",
                "start stopwatch",
                "start countdown",
            ],
            dependencies=["sqlite3"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            # Legacy math & stopwatch tools
            ToolSpec(
                name="productivity.calculate",
                description="Safely evaluate a mathematical calculation without eval.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.calculate,
            ),
            ToolSpec(
                name="productivity.start_stopwatch",
                description="Start a stopwatch timer.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.start_stopwatch,
            ),
            ToolSpec(
                name="productivity.stop_stopwatch",
                description="Stop the active stopwatch timer.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.stop_stopwatch,
            ),
            ToolSpec(
                name="productivity.start_countdown",
                description="Start a background countdown for N seconds.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.start_countdown,
            ),

            # Task management tools
            ToolSpec(
                name="productivity.create_task",
                description="Create a new tracked user task or to-do item.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.create_task,
            ),
            ToolSpec(
                name="productivity.list_tasks",
                description="List tracked user tasks with optional status and priority filtering.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.list_tasks,
            ),
            ToolSpec(
                name="productivity.update_task",
                description="Update fields on an existing user task.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.update_task,
            ),
            ToolSpec(
                name="productivity.complete_task",
                description="Mark a user task as completed.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.complete_task,
            ),
            ToolSpec(
                name="productivity.delete_task",
                description="Permanently delete a user task (requires confirmation).",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.delete_task,
            ),

            # Reminder management tools
            ToolSpec(
                name="productivity.add_reminder",
                description="Schedule a new reminder with atomic lease tracking and optional recurrence.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.add_reminder,
            ),
            ToolSpec(
                name="productivity.list_reminders",
                description="List active scheduled reminders.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.list_reminders,
            ),
            ToolSpec(
                name="productivity.reschedule_reminder",
                description="Reschedule an existing reminder to a new time.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.reschedule_reminder,
            ),
            ToolSpec(
                name="productivity.cancel_reminder",
                description="Cancel an active reminder.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.cancel_reminder,
            ),
            ToolSpec(
                name="productivity.complete_reminder",
                description="Mark a reminder as completed.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.complete_reminder,
            ),
            ToolSpec(
                name="productivity.delete_reminder",
                description="Permanently delete a scheduled reminder (requires confirmation).",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.delete_reminder,
            ),

            # Notes management tools
            ToolSpec(
                name="productivity.save_note",
                description="Save a new searchable personal note.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.save_note,
            ),
            ToolSpec(
                name="productivity.list_notes",
                description="List recent user notes.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.list_notes,
            ),
            ToolSpec(
                name="productivity.search_notes",
                description="Search user notes using SQLite FTS5 full-text search.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.search_notes,
            ),
            ToolSpec(
                name="productivity.delete_note",
                description="Permanently delete a note (requires confirmation).",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.delete_note,
            ),

            # Daily plan & briefing tool
            ToolSpec(
                name="productivity.get_daily_plan",
                description="Retrieve aggregated daily plan and AI morning briefing.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.get_daily_plan,
            ),
        ]

    # -------------------------------------------------------------------------
    # LEGACY MATH & STOPWATCH HANDLERS
    # -------------------------------------------------------------------------

    def calculate(self, expression: str) -> ToolResult:
        try:
            val = safe_eval_math(expression)
            return ToolResult(status="SUCCESS", message=f"Result: {val}", data={"result": val})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Calculation error: {exc}", error=str(exc))

    def start_stopwatch(self) -> ToolResult:
        res = self.productivity.start_stopwatch()
        return ToolResult(status="SUCCESS", message=res)

    def stop_stopwatch(self) -> ToolResult:
        res = self.productivity.stop_stopwatch()
        return ToolResult(status="SUCCESS", message=res)

    def start_countdown(self, seconds: int) -> ToolResult:
        res = self.productivity.start_countdown(seconds)
        return ToolResult(status="SUCCESS", message=res, data={"seconds": seconds})

    # -------------------------------------------------------------------------
    # TASK HANDLERS
    # -------------------------------------------------------------------------

    def create_task(
        self,
        title: str,
        description: str = "",
        due_date: Optional[str] = None,
        priority: str = "normal",
    ) -> ToolResult:
        try:
            task = self.service.store.create_task(
                title=title,
                description=description,
                due_date=due_date,
                priority=priority,
            )
            msg = f"Task created: '{task.title}' (ID: {task.id}, Priority: {task.priority})"
            if task.due_date:
                msg += f", Due: {task.due_date}"
            return ToolResult(status="SUCCESS", message=msg, data=task.to_dict())
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to create task: {exc}", error=str(exc))

    def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> ToolResult:
        try:
            tasks = self.service.store.list_tasks(status=status, priority=priority, limit=limit)
            if not tasks:
                return ToolResult(status="SUCCESS", message="No tasks found matching criteria.", data={"tasks": []})

            lines = [f"Found {len(tasks)} task(s):"]
            for t in tasks:
                due_info = f" [Due: {t.due_date[:16]}]" if t.due_date else ""
                lines.append(f"- [{t.id}] ({t.priority.upper()}) {t.title} - status: {t.status}{due_info}")

            return ToolResult(status="SUCCESS", message="\n".join(lines), data={"tasks": [t.to_dict() for t in tasks]})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to list tasks: {exc}", error=str(exc))

    def update_task(
        self,
        task_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
    ) -> ToolResult:
        try:
            t_id = int(task_id)
            task = self.service.store.update_task(
                task_id=t_id,
                title=title,
                description=description,
                due_date=due_date,
                priority=priority,
                status=status,
            )
            if not task:
                return ToolResult(status="FAILED", message=f"Task with ID {t_id} not found.", error="NotFound")
            return ToolResult(status="SUCCESS", message=f"Task {t_id} updated successfully.", data=task.to_dict())
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to update task: {exc}", error=str(exc))

    def complete_task(self, task_id: int) -> ToolResult:
        try:
            t_id = int(task_id)
            task = self.service.store.complete_task(t_id)
            if not task:
                return ToolResult(status="FAILED", message=f"Task with ID {t_id} not found.", error="NotFound")
            return ToolResult(status="SUCCESS", message=f"Task '{task.title}' marked as completed.", data=task.to_dict())
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to complete task: {exc}", error=str(exc))

    def delete_task(self, task_id: int) -> ToolResult:
        try:
            t_id = int(task_id)
            deleted = self.service.store.delete_task(t_id)
            if not deleted:
                return ToolResult(status="FAILED", message=f"Task with ID {t_id} not found.", error="NotFound")
            return ToolResult(status="SUCCESS", message=f"Task {t_id} deleted successfully.", data={"task_id": t_id})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to delete task: {exc}", error=str(exc))

    # -------------------------------------------------------------------------
    # REMINDER HANDLERS
    # -------------------------------------------------------------------------

    def add_reminder(
        self,
        title: str,
        remind_at: Optional[str] = None,
        recurrence: str = "none",
        priority: str = "normal",
    ) -> ToolResult:
        try:
            target_time = remind_at
            clean_title = title.strip()

            # If remind_at was omitted, try to extract natural time from title
            if not target_time:
                time_patterns = [
                    r"\bin\s+\d+\s*(?:s(?:ec)?|m(?:in)?|h(?:our)?|d(?:ay)?|w(?:eek)?)s?\b",
                    r"\btomorrow(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?\b",
                    r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
                    r"\bon\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                ]
                extracted = None
                for pat in time_patterns:
                    m = re.search(pat, clean_title, re.IGNORECASE)
                    if m:
                        extracted = m.group(0)
                        clean_title = re.sub(pat, "", clean_title, flags=re.IGNORECASE).strip()
                        break
                target_time = extracted if extracted else "in 15 minutes"

            reminder = self.service.store.add_reminder(
                title=clean_title,
                remind_at=target_time,
                recurrence=recurrence,
                priority=priority,
            )
            msg = f"Reminder set: '{reminder.title}' for {reminder.remind_at}"
            if reminder.recurrence and reminder.recurrence != "none":
                msg += f" (repeats: {reminder.recurrence})"
            return ToolResult(status="SUCCESS", message=msg, data=reminder.to_dict())
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to add reminder: {exc}", error=str(exc))

    def list_reminders(self, status: Optional[str] = None, limit: int = 50) -> ToolResult:
        try:
            reminders = self.service.store.list_reminders(status=status, limit=limit)
            if not reminders:
                return ToolResult(status="SUCCESS", message="No active reminders found.", data={"reminders": []})

            lines = [f"Found {len(reminders)} active reminder(s):"]
            for r in reminders:
                rec_str = f" [Repeats: {r.recurrence}]" if r.recurrence and r.recurrence != "none" else ""
                lines.append(f"- [{r.id}] '{r.title}' at {r.remind_at} (status: {r.status}){rec_str}")

            return ToolResult(
                status="SUCCESS",
                message="\n".join(lines),
                data={"reminders": [r.to_dict() for r in reminders]},
            )
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to list reminders: {exc}", error=str(exc))

    def reschedule_reminder(self, reminder_id: int, new_remind_at: str) -> ToolResult:
        try:
            r_id = int(reminder_id)
            reminder = self.service.store.reschedule_reminder(r_id, new_remind_at)
            if not reminder:
                return ToolResult(status="FAILED", message=f"Reminder with ID {r_id} not found.", error="NotFound")
            return ToolResult(
                status="SUCCESS",
                message=f"Reminder {r_id} rescheduled to {reminder.remind_at}.",
                data=reminder.to_dict(),
            )
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to reschedule reminder: {exc}", error=str(exc))

    def cancel_reminder(self, reminder_id: int) -> ToolResult:
        try:
            r_id = int(reminder_id)
            reminder = self.service.store.cancel_reminder(r_id)
            if not reminder:
                return ToolResult(status="FAILED", message=f"Reminder with ID {r_id} not found.", error="NotFound")
            return ToolResult(status="SUCCESS", message=f"Reminder {r_id} cancelled.", data=reminder.to_dict())
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to cancel reminder: {exc}", error=str(exc))

    def complete_reminder(self, reminder_id: int) -> ToolResult:
        try:
            r_id = int(reminder_id)
            reminder = self.service.store.complete_reminder(r_id)
            if not reminder:
                return ToolResult(status="FAILED", message=f"Reminder with ID {r_id} not found.", error="NotFound")
            return ToolResult(status="SUCCESS", message=f"Reminder {r_id} marked complete.", data=reminder.to_dict())
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to complete reminder: {exc}", error=str(exc))

    def delete_reminder(self, reminder_id: int) -> ToolResult:
        try:
            r_id = int(reminder_id)
            deleted = self.service.store.delete_reminder(r_id)
            if not deleted:
                return ToolResult(status="FAILED", message=f"Reminder with ID {r_id} not found.", error="NotFound")
            return ToolResult(status="SUCCESS", message=f"Reminder {r_id} deleted successfully.", data={"reminder_id": r_id})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to delete reminder: {exc}", error=str(exc))

    # -------------------------------------------------------------------------
    # NOTES HANDLERS
    # -------------------------------------------------------------------------

    def save_note(self, title: str, content: str) -> ToolResult:
        try:
            note = self.service.store.save_note(title=title, content=content)
            return ToolResult(
                status="SUCCESS",
                message=f"Note saved: '{note.title}' (ID: {note.id})",
                data=note.to_dict(),
            )
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to save note: {exc}", error=str(exc))

    def list_notes(self, limit: int = 50) -> ToolResult:
        try:
            notes = self.service.store.list_notes(limit=limit)
            if not notes:
                return ToolResult(status="SUCCESS", message="No saved notes found.", data={"notes": []})

            lines = [f"Found {len(notes)} note(s):"]
            for n in notes:
                preview = (n.content[:60] + "...") if len(n.content) > 60 else n.content
                lines.append(f"- [{n.id}] {n.title}: \"{preview}\"")

            return ToolResult(status="SUCCESS", message="\n".join(lines), data={"notes": [n.to_dict() for n in notes]})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to list notes: {exc}", error=str(exc))

    def search_notes(self, query: str, limit: int = 20) -> ToolResult:
        try:
            notes = self.service.store.search_notes(query=query, limit=limit)
            if not notes:
                return ToolResult(status="SUCCESS", message=f"No notes matching '{query}'.", data={"notes": []})

            lines = [f"Search results for '{query}' ({len(notes)} match(es)):"]
            for n in notes:
                preview = (n.content[:70] + "...") if len(n.content) > 70 else n.content
                lines.append(f"- [{n.id}] {n.title}: \"{preview}\"")

            return ToolResult(status="SUCCESS", message="\n".join(lines), data={"notes": [n.to_dict() for n in notes]})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to search notes: {exc}", error=str(exc))

    def delete_note(self, note_id: int) -> ToolResult:
        try:
            n_id = int(note_id)
            deleted = self.service.store.delete_note(n_id)
            if not deleted:
                return ToolResult(status="FAILED", message=f"Note with ID {n_id} not found.", error="NotFound")
            return ToolResult(status="SUCCESS", message=f"Note {n_id} deleted successfully.", data={"note_id": n_id})
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to delete note: {exc}", error=str(exc))

    # -------------------------------------------------------------------------
    # DAILY PLAN HANDLER
    # -------------------------------------------------------------------------

    def get_daily_plan(self, date: Optional[str] = None) -> ToolResult:
        try:
            plan = self.service.get_daily_plan(target_date_iso=date)
            return ToolResult(status="SUCCESS", message=plan.summary_text, data=plan.to_dict())
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to get daily plan: {exc}", error=str(exc))
