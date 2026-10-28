"""Agent task planning and execution skill for OLIVER 2.0."""

from __future__ import annotations

from typing import Any
from agent.executor import get_agent_task_loop
from agent.persistence import TaskStore
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class AgentSkill(BaseSkill):
    """Adapter wrapping the OLIVER 2.0 Multi-Step Agent Task Loop and Planner."""

    def __init__(self) -> None:
        super().__init__()
        self.task_loop = get_agent_task_loop()
        self.store = TaskStore()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="agent",
            version="1.0.0",
            description="Multi-step task decomposition, planning, and verified autonomous execution.",
            triggers=[
                "plan and execute",
                "run task",
                "task status",
            ],
            dependencies=["sqlite3"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="agent.run_task",
                description="Decompose a composite goal into a bounded multi-step plan and execute it.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.run_task,
            ),
            ToolSpec(
                name="agent.task_status",
                description="Check current progress or outcome of an agent task by task ID.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.task_status,
            ),
        ]

    def run_task(self, goal: str = "", task_id: str = "") -> ToolResult:
        if not goal.strip():
            return ToolResult(status="FAILED", message="Please specify a task or goal to execute.")

        report = self.task_loop.run(goal=goal.strip(), task_id=task_id.strip() or None)
        status = "SUCCESS" if report.is_success else "FAILED"
        if report.overall_status in ("WAITING_CONFIRMATION", "CANCELLED", "TIMEOUT"):
            status = report.overall_status

        return ToolResult(
            status=status,
            message=report.summary,
            data=report.to_dict(),
        )

    def task_status(self, task_id: str = "") -> ToolResult:
        if not task_id.strip():
            return ToolResult(status="FAILED", message="Please provide a valid task ID.")

        task_data = self.store.get_task(task_id.strip())
        if not task_data:
            return ToolResult(status="FAILED", message=f"No task found with ID '{task_id.strip()}'.")

        steps = self.store.get_task_steps(task_id.strip())
        summary = (
            f"Task {task_id.strip()}: Status={task_data['status']}, "
            f"Step={task_data['current_step']}, Completed Steps={len(steps)}"
        )
        return ToolResult(
            status="SUCCESS",
            message=summary,
            data={"task": task_data, "steps": [s.to_dict() for s in steps]},
        )
