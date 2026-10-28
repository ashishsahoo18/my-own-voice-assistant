"""Persistence store for agent tasks, plans, and step outcomes in the unified SQLite database."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from agent.models import Plan, PlanStep, StepResult
from core.logging import get_logger
from memory.unified_db import UnifiedDatabase, get_unified_db

logger = get_logger("agent.persistence")


class TaskStore:
    """Manages transactional persistence of agent task states and step verification outcomes."""

    def __init__(self, db: Optional[UnifiedDatabase] = None) -> None:
        self.db = db or get_unified_db()

    def save_task(self, task_id: str, goal: str, plan: Plan, status: str = "IN_PROGRESS") -> None:
        """Create or update the root task record with initial plan."""
        now = datetime.now().isoformat()
        plan_json = json.dumps(plan.to_dict())

        self.db.execute(
            """
            INSERT INTO agent_tasks (task_id, goal, status, plan_json, current_step, replan_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                status = excluded.status,
                plan_json = excluded.plan_json,
                current_step = excluded.current_step,
                replan_count = excluded.replan_count,
                updated_at = excluded.updated_at
            """,
            (
                task_id,
                goal,
                status,
                plan_json,
                plan.current_step_index,
                plan.replan_count,
                now,
                now,
            ),
        )

    def update_task_status(
        self,
        task_id: str,
        status: str,
        current_step: int,
        replan_count: int = 0,
        plan: Optional[Plan] = None,
    ) -> None:
        """Update current step progression, replan count, or final completion status."""
        now = datetime.now().isoformat()
        if plan:
            plan_json = json.dumps(plan.to_dict())
            self.db.execute(
                """
                UPDATE agent_tasks
                SET status = ?, current_step = ?, replan_count = ?, plan_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status, current_step, replan_count, plan_json, now, task_id),
            )
        else:
            self.db.execute(
                """
                UPDATE agent_tasks
                SET status = ?, current_step = ?, replan_count = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status, current_step, replan_count, now, task_id),
            )

    def save_step_result(self, task_id: str, result: StepResult, tool_args: Optional[dict[str, Any]] = None) -> None:
        """Persist verified step execution outcome."""
        args_str = json.dumps(tool_args or {})
        now = datetime.now().isoformat()
        evidence_str = (
            json.dumps(result.verification_evidence)
            if isinstance(result.verification_evidence, (dict, list))
            else str(result.verification_evidence or "")
        )
        msg_str = str(result.message or "")

        self.db.execute(
            """
            INSERT INTO agent_task_steps (
                task_id, step_number, tool_name, arguments, status,
                verification_status, verification_evidence, message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id, step_number) DO UPDATE SET
                status = excluded.status,
                verification_status = excluded.verification_status,
                verification_evidence = excluded.verification_evidence,
                message = excluded.message
            """,
            (
                task_id,
                result.step_number,
                result.tool_name,
                args_str,
                result.status,
                result.verification_status,
                evidence_str,
                msg_str,
                now,
            ),
        )

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Retrieve task record by task ID."""
        row = self.db.fetch_one("SELECT * FROM agent_tasks WHERE task_id = ?", (task_id,))
        if not row:
            return None
        d = dict(row)
        try:
            d["plan"] = json.loads(d["plan_json"])
        except Exception:
            d["plan"] = {}
        return d

    def get_task_steps(self, task_id: str) -> list[StepResult]:
        """Retrieve all completed step records for a task in execution order."""
        rows = self.db.fetch_all(
            "SELECT * FROM agent_task_steps WHERE task_id = ? ORDER BY step_number ASC",
            (task_id,),
        )
        results = []
        for r in rows:
            results.append(
                StepResult(
                    step_number=r["step_number"],
                    tool_name=r["tool_name"],
                    status=r["status"],
                    message=r["message"],
                    verification_status=r["verification_status"],
                    verification_evidence=r["verification_evidence"],
                    timestamp=r["created_at"],
                )
            )
        return results

    def get_resumable_task(self, task_id: str) -> Optional[tuple[Plan, list[StepResult]]]:
        """Return plan and already-completed verified steps for resuming interrupted tasks."""
        task_data = self.get_task(task_id)
        if not task_data or not task_data.get("plan"):
            return None

        plan = Plan.from_dict(task_data["plan"])
        completed_steps = self.get_task_steps(task_id)
        return plan, completed_steps

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent tasks with status and progression."""
        rows = self.db.fetch_all(
            "SELECT task_id, goal, status, current_step, replan_count, created_at, updated_at FROM agent_tasks ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]
