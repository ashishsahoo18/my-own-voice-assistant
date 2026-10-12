"""Authoritative multi-step agent task loop coordinating validation, policy, execution, and verification."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from agent.loop_detector import LoopDetector, LoopDetectedError
from agent.models import Plan, PlanStep, StepResult, TaskReport
from agent.persistence import TaskStore
from agent.planner import Planner
from agent.validator import PlanValidator, PlanValidationError
from core.config import get_config
from core.logging import get_logger
from execution.engine import ExecutionEngine, get_execution_engine
from execution.request import TaskRequest
from memory.manager import HybridMemoryEngine, get_memory_engine
from security.confirmation import ConfirmationManager, get_confirmation_manager
from security.kill_switch import KillSwitch, get_kill_switch

logger = get_logger("agent.executor")


class AgentTaskLoop:
    """Executes validated multi-step plans through the authoritative ExecutionEngine funnel."""

    def __init__(
        self,
        engine: Optional[ExecutionEngine] = None,
        planner: Optional[Planner] = None,
        validator: Optional[PlanValidator] = None,
        loop_detector: Optional[LoopDetector] = None,
        store: Optional[TaskStore] = None,
        memory: Optional[HybridMemoryEngine] = None,
        kill_switch: Optional[KillSwitch] = None,
        confirmation_mgr: Optional[ConfirmationManager] = None,
    ) -> None:
        self.engine = engine or get_execution_engine()
        self.planner = planner or Planner()
        self.validator = validator or PlanValidator()
        self.loop_detector = loop_detector or LoopDetector()
        self.store = store or TaskStore()
        self.memory = memory or get_memory_engine()
        self.kill_switch = kill_switch or get_kill_switch()
        self.confirmation_mgr = confirmation_mgr or get_confirmation_manager()
        self.config = get_config()

        self.max_plan_steps = self.config.agent.max_plan_steps
        self.max_replans = self.config.agent.max_replans
        self.max_tool_calls = self.config.agent.max_tool_calls
        self.task_timeout_s = self.config.agent.task_timeout_seconds
        self.step_timeout_s = self.config.agent.step_timeout_seconds
        self.require_step_verification = self.config.agent.require_step_verification

        self._cancelled_tasks: set[str] = set()

    def cancel(self, task_id: str) -> None:
        """Mark a task as cancelled."""
        self._cancelled_tasks.add(task_id)

    def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled_tasks or self.kill_switch.is_active

    def run(
        self,
        goal: str,
        task_id: Optional[str] = None,
        session_id: str = "default",
        user_confirmed: bool = False,
        plan_override: Optional[Plan] = None,
    ) -> TaskReport:
        """Execute a complete multi-step task for a given user goal."""
        tid = task_id or f"task_{uuid.uuid4().hex[:12]}"
        start_time = time.time()
        self.loop_detector.reset()

        # 1. Kill Switch & Cancellation pre-check
        if self.is_cancelled(tid):
            return TaskReport(
                task_id=tid,
                goal=goal,
                overall_status="CANCELLED",
                summary="Task cancelled prior to execution by Kill Switch or user cancellation.",
                total_duration_seconds=round(time.time() - start_time, 3),
            )

        # 2. Plan generation (or use validated override)
        if plan_override:
            plan = plan_override
        else:
            plan = self.planner.plan(goal=goal, session_id=session_id)

        # 3. Plan validation
        is_valid, validation_errors = self.validator.validate(plan)
        if not is_valid:
            err_msg = "; ".join(validation_errors)
            self.store.save_task(tid, goal, plan, status="VALIDATION_FAILED")
            return TaskReport(
                task_id=tid,
                goal=goal,
                overall_status="FAILED",
                summary=f"Plan validation failed: {err_msg}",
                total_duration_seconds=round(time.time() - start_time, 3),
            )

        # 4. Save initial task state
        self.store.save_task(tid, goal, plan, status="IN_PROGRESS")

        # 5. Execute steps loop
        return self._execute_plan_loop(
            task_id=tid,
            goal=goal,
            plan=plan,
            session_id=session_id,
            user_confirmed=user_confirmed,
            start_time=start_time,
            completed_steps=[],
            tool_calls_count=0,
        )

    def resume(
        self,
        task_id: str,
        session_id: str = "default",
        user_confirmed: bool = False,
    ) -> TaskReport:
        """Resume an interrupted task without repeating already verified completed steps."""
        start_time = time.time()
        resumable = self.store.get_resumable_task(task_id)
        if not resumable:
            return TaskReport(
                task_id=task_id,
                goal="",
                overall_status="FAILED",
                summary=f"No resumable task found with ID '{task_id}'.",
                total_duration_seconds=0.0,
            )

        plan, completed_steps = resumable
        goal = plan.goal

        # Find which steps remain to be executed
        completed_step_nums = {s.step_number for s in completed_steps if s.status == "SUCCESS"}
        remaining_steps = [s for s in plan.steps if s.step_number not in completed_step_nums]

        if not remaining_steps:
            return TaskReport(
                task_id=task_id,
                goal=goal,
                overall_status="SUCCESS",
                steps_executed=completed_steps,
                summary="All steps were already completed and verified.",
                total_duration_seconds=round(time.time() - start_time, 3),
            )

        plan.steps = remaining_steps
        self.loop_detector.reset()
        self.store.update_task_status(task_id, "IN_PROGRESS", current_step=len(completed_steps), plan=plan)

        return self._execute_plan_loop(
            task_id=task_id,
            goal=goal,
            plan=plan,
            session_id=session_id,
            user_confirmed=user_confirmed,
            start_time=start_time,
            completed_steps=completed_steps,
            tool_calls_count=len(completed_steps),
        )

    def _execute_plan_loop(
        self,
        task_id: str,
        goal: str,
        plan: Plan,
        session_id: str,
        user_confirmed: bool,
        start_time: float,
        completed_steps: list[StepResult],
        tool_calls_count: int,
    ) -> TaskReport:
        """Main execution loop iterating sequentially through plan steps."""
        all_step_results: list[StepResult] = list(completed_steps)
        current_calls = tool_calls_count
        replan_attempts = plan.replan_count

        step_idx = 0
        while step_idx < len(plan.steps):
            step = plan.steps[step_idx]

            # A. Check Cancellation & Kill Switch
            if self.is_cancelled(task_id):
                self.store.update_task_status(task_id, "CANCELLED", current_step=step.step_number, replan_count=replan_attempts)
                return self._build_report(
                    task_id=task_id,
                    goal=goal,
                    overall_status="CANCELLED",
                    step_results=all_step_results,
                    start_time=start_time,
                    replan_count=replan_attempts,
                    summary_prefix="Execution cancelled by Kill Switch or user request.",
                )

            # B. Check Resource Limits: Timeout
            elapsed = time.time() - start_time
            if elapsed > self.task_timeout_s:
                self.store.update_task_status(task_id, "TIMEOUT", current_step=step.step_number, replan_count=replan_attempts)
                timeout_res = StepResult(
                    step_number=step.step_number,
                    tool_name=step.tool_name,
                    status="TIMEOUT",
                    message=f"Task execution exceeded overall time limit ({self.task_timeout_s}s).",
                    verification_status="FAILED",
                )
                all_step_results.append(timeout_res)
                return self._build_report(
                    task_id=task_id,
                    goal=goal,
                    overall_status="TIMEOUT",
                    step_results=all_step_results,
                    start_time=start_time,
                    replan_count=replan_attempts,
                    summary_prefix=f"Task timed out after {elapsed:.1f}s.",
                )

            # C. Check Resource Limits: Maximum tool invocations
            if current_calls >= self.max_tool_calls:
                self.store.update_task_status(task_id, "FAILED", current_step=step.step_number, replan_count=replan_attempts)
                limit_res = StepResult(
                    step_number=step.step_number,
                    tool_name=step.tool_name,
                    status="FAILED",
                    message=f"Hard limit on tool invocations ({self.max_tool_calls}) reached.",
                    verification_status="FAILED",
                )
                all_step_results.append(limit_res)
                return self._build_report(
                    task_id=task_id,
                    goal=goal,
                    overall_status="FAILED",
                    step_results=all_step_results,
                    start_time=start_time,
                    replan_count=replan_attempts,
                    summary_prefix="Exceeded maximum tool calls limit.",
                )

            # D. Loop & Oscillation Detection
            try:
                self.loop_detector.check_or_raise(step.tool_name, step.arguments)
            except LoopDetectedError as loop_err:
                loop_res = StepResult(
                    step_number=step.step_number,
                    tool_name=step.tool_name,
                    status="FAILED",
                    message=str(loop_err),
                    verification_status="FAILED",
                )
                all_step_results.append(loop_res)
                self.store.save_step_result(task_id, loop_res, step.arguments)
                self.store.update_task_status(task_id, "FAILED", current_step=step.step_number, replan_count=replan_attempts)
                return self._build_report(
                    task_id=task_id,
                    goal=goal,
                    overall_status="FAILED",
                    step_results=all_step_results,
                    start_time=start_time,
                    replan_count=replan_attempts,
                    summary_prefix=f"Execution halted: {loop_err}",
                )

            # E. Confirmation Enforcement
            if step.requires_confirmation and not user_confirmed:
                confirm_res = StepResult(
                    step_number=step.step_number,
                    tool_name=step.tool_name,
                    status="WAITING_CONFIRMATION",
                    message=f"Action '{step.tool_name}' requires explicit user confirmation.",
                    verification_status="UNVERIFIED",
                )
                all_step_results.append(confirm_res)
                self.store.save_step_result(task_id, confirm_res, step.arguments)
                self.store.update_task_status(task_id, "WAITING_CONFIRMATION", current_step=step.step_number, replan_count=replan_attempts)
                return self._build_report(
                    task_id=task_id,
                    goal=goal,
                    overall_status="WAITING_CONFIRMATION",
                    step_results=all_step_results,
                    start_time=start_time,
                    replan_count=replan_attempts,
                    summary_prefix=f"Step {step.step_number} ({step.tool_name}) paused awaiting human confirmation.",
                )

            # F. Execute Action through Authoritative ExecutionEngine
            current_calls += 1
            task_req = TaskRequest(
                tool_name=step.tool_name,
                arguments=step.arguments,
                user_confirmed=user_confirmed,
                timeout_s=self.step_timeout_s,
                metadata={"task_id": task_id, "step_number": step.step_number, "session_id": session_id},
            )

            exec_res = self.engine.execute(task_req)

            # G. Evaluate Step Verification and Status
            is_step_success = False
            verif_status = exec_res.status  # VERIFIED, UNVERIFIED, FAILED, DENIED, CANCELLED, TIMEOUT

            if exec_res.status == "VERIFIED":
                is_step_success = True
                step_status = "SUCCESS"
            elif exec_res.status == "UNVERIFIED":
                if self.require_step_verification:
                    # Strict verification mode: UNVERIFIED is treated as a halting failure
                    is_step_success = False
                    step_status = "UNVERIFIED"
                else:
                    is_step_success = True
                    step_status = "SUCCESS"
            elif exec_res.status == "DENIED":
                step_status = "DENIED"
            elif exec_res.status == "CANCELLED":
                step_status = "CANCELLED"
            elif exec_res.status == "TIMEOUT":
                step_status = "TIMEOUT"
            else:
                step_status = "FAILED"

            step_outcome = StepResult(
                step_number=step.step_number,
                tool_name=step.tool_name,
                status=step_status,
                message=exec_res.message,
                verification_status=verif_status if verif_status in ("VERIFIED", "UNVERIFIED", "FAILED") else "FAILED",
                verification_evidence=exec_res.evidence,
                error=exec_res.error,
            )

            all_step_results.append(step_outcome)
            self.store.save_step_result(task_id, step_outcome, step.arguments)

            # H. Update working memory with observable entities
            if is_step_success and exec_res.data:
                for k, v in exec_res.data.items():
                    if k in ("created_file", "created_folder", "target", "path") and isinstance(v, str):
                        self.memory.working.track_entity(session_id, k, v)

            # I. Step-by-Step Flow Control
            if is_step_success:
                # Proceed to next step
                step_idx += 1
                self.store.update_task_status(
                    task_id,
                    "IN_PROGRESS",
                    current_step=step.step_number,
                    replan_count=replan_attempts,
                )
            else:
                # Step failed or denied
                if step_status in ("DENIED", "CANCELLED"):
                    # Non-recoverable policy denial: halt immediately
                    self.store.update_task_status(task_id, step_status, current_step=step.step_number, replan_count=replan_attempts)
                    return self._build_report(
                        task_id=task_id,
                        goal=goal,
                        overall_status=step_status,
                        step_results=all_step_results,
                        start_time=start_time,
                        replan_count=replan_attempts,
                        summary_prefix=f"Step {step.step_number} ({step.tool_name}) was blocked by policy: {exec_res.message}",
                    )

                # Recoverable failure: check replan budget (max 1 replan)
                if replan_attempts < self.max_replans:
                    logger.info("Attempting recovery replan for task %s (step %d failed)", task_id, step.step_number)
                    replan_attempts += 1
                    new_plan = self.planner.replan(
                        goal=goal,
                        completed_steps=[s for s in all_step_results if s.status == "SUCCESS"],
                        failed_step=step_outcome,
                        failure_reason=exec_res.message,
                        session_id=session_id,
                    )
                    if new_plan and new_plan.steps:
                        # Validate replan
                        is_replan_valid, replan_errs = self.validator.validate(new_plan)
                        if is_replan_valid:
                            plan = new_plan
                            plan.replan_count = replan_attempts
                            step_idx = 0
                            self.store.update_task_status(task_id, "REPLANNING", current_step=step.step_number, replan_count=replan_attempts, plan=plan)
                            continue

                # Replanning either unavailable, exhausted, or failed
                final_status = "REPLAN_EXHAUSTED" if replan_attempts >= self.max_replans else "FAILED"
                self.store.update_task_status(task_id, final_status, current_step=step.step_number, replan_count=replan_attempts)
                return self._build_report(
                    task_id=task_id,
                    goal=goal,
                    overall_status=final_status,
                    step_results=all_step_results,
                    start_time=start_time,
                    replan_count=replan_attempts,
                    summary_prefix=f"Step {step.step_number} ({step.tool_name}) failed: {exec_res.message}",
                )

        # All steps completed successfully
        self.store.update_task_status(task_id, "SUCCESS", current_step=len(plan.steps), replan_count=replan_attempts)
        return self._build_report(
            task_id=task_id,
            goal=goal,
            overall_status="SUCCESS",
            step_results=all_step_results,
            start_time=start_time,
            replan_count=replan_attempts,
            summary_prefix="All planned steps executed and verified successfully.",
        )

    def _build_report(
        self,
        task_id: str,
        goal: str,
        overall_status: str,
        step_results: list[StepResult],
        start_time: float,
        replan_count: int,
        summary_prefix: str,
    ) -> TaskReport:
        """Construct an honest post-execution report strictly grounded in real tool outcomes."""
        duration = round(time.time() - start_time, 3)

        verified_count = sum(1 for s in step_results if s.verification_status == "VERIFIED")
        lines = [
            f"**Task Summary**: {summary_prefix}",
            f"- **Goal**: {goal}",
            f"- **Status**: {overall_status}",
            f"- **Steps Executed**: {len(step_results)} (Verified: {verified_count})",
            f"- **Duration**: {duration}s",
            f"- **Replans**: {replan_count}",
            "",
            "**Step Details**:",
        ]
        for s in step_results:
            verif_badge = f"[{s.verification_status}]" if s.verification_status else "[UNVERIFIED]"
            evidence_str = f" (Evidence: {s.verification_evidence})" if s.verification_evidence else ""
            lines.append(f"{s.step_number}. `{s.tool_name}`: {s.status} {verif_badge} - {s.message}{evidence_str}")

        summary = "\n".join(lines)
        return TaskReport(
            task_id=task_id,
            goal=goal,
            overall_status=overall_status,
            steps_executed=step_results,
            summary=summary,
            total_duration_seconds=duration,
            replan_count=replan_count,
        )


_default_task_loop: Optional[AgentTaskLoop] = None


def get_agent_task_loop() -> AgentTaskLoop:
    """Return singleton instance of AgentTaskLoop."""
    global _default_task_loop
    if _default_task_loop is None:
        _default_task_loop = AgentTaskLoop()
    return _default_task_loop
