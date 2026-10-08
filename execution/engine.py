"""Central Execution and Verification Engine for OLIVER 2.0.

All actions across OLIVER mode, legacy mode, and direct tool invocations funnel
through this authoritative pipeline:
TaskRequest -> Validate -> PolicyGate -> Confirm -> Execute -> Verify -> Record -> Report
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any, Callable, Optional

from core.logging import get_audit_logger
from execution.request import TaskRequest
from execution.verifiers import VerifierRegistry
from security.kill_switch import get_kill_switch
from security.policy_engine import PolicyDecisionType, get_policy_engine
from skills.base import ToolResult, ToolRiskLevel
from skills.registry import get_registry

logger = logging.getLogger("oliver.execution.engine")


class ExecutionEngine:
    """Authoritative execution funnel for all tool and command invocations."""

    def __init__(
        self,
        registry: Optional[Any] = None,
        verifier_registry: Optional[VerifierRegistry] = None,
        max_fallback_retries: int = 1,
    ) -> None:
        self.registry = registry
        self.verifier_registry = verifier_registry or VerifierRegistry()
        self.max_fallback_retries = max_fallback_retries
        self._fallback_handlers: dict[str, Callable[..., Any]] = {}

    def register_fallback(self, tool_name: str, handler: Callable[..., Any]) -> None:
        """Register a safe secondary execution handler for a specific tool."""
        self._fallback_handlers[tool_name.strip().lower()] = handler

    def execute(self, request: TaskRequest, registry: Optional[Any] = None) -> ToolResult:
        """Execute a structured TaskRequest through the complete verified lifecycle."""
        audit = get_audit_logger()
        corr_id = request.correlation_id

        # 1. Lifecycle: REQUESTED
        audit.record_event(
            event_type="TASK_REQUESTED",
            action=request.tool_name,
            risk_level=request.risk_level or 0,
            status="RECEIVED",
            details={"request_id": request.request_id, "correlation_id": corr_id},
        )

        # 2. Validation
        is_valid, val_err = request.validate_integrity()
        if not is_valid:
            audit.record_event(
                event_type="TASK_VALIDATION_FAILED",
                action=request.tool_name,
                risk_level=request.risk_level or 0,
                status="FAILED",
                details={"correlation_id": corr_id, "error": val_err},
            )
            return ToolResult(
                status="FAILED",
                message=f"TaskRequest validation failed: {val_err}",
                error="ValidationError",
            )

        audit.record_event(
            event_type="TASK_VALIDATED",
            action=request.tool_name,
            risk_level=request.risk_level or 0,
            status="VALIDATED",
            details={"correlation_id": corr_id},
        )

        # 3. Emergency Kill Switch Pre-Check
        kill_switch = get_kill_switch()
        if kill_switch.is_active:
            audit.record_event(
                event_type="EXECUTION_CANCELLED",
                action=request.tool_name,
                risk_level=request.risk_level or 0,
                status="CANCELLED",
                details={"correlation_id": corr_id, "reason": kill_switch.reason},
            )
            return ToolResult(
                status="CANCELLED",
                message=f"Operation cancelled: Emergency kill switch is active ({kill_switch.reason}).",
                error="KillSwitchEngaged",
            )

        # 4. Tool Specification Lookup
        reg = registry or self.registry or get_registry()
        tool = reg.get_tool(request.tool_name)
        if not tool:
            audit.record_event(
                event_type="TASK_FAILED",
                action=request.tool_name,
                risk_level=request.risk_level or 0,
                status="NOT_FOUND",
                details={"correlation_id": corr_id, "error": "Tool not registered"},
            )
            return ToolResult(
                status="FAILED",
                message=f"Tool '{request.tool_name}' is not registered in SkillRegistry.",
                error="ToolNotFound",
            )

        risk_level = int(request.risk_level if request.risk_level is not None else tool.risk_level)

        # 5. Policy Gate Evaluation
        policy_engine = get_policy_engine()
        decision = policy_engine.evaluate(
            tool_name=request.tool_name,
            risk_level=risk_level,
            arguments=request.arguments,
            user_confirmed=request.user_confirmed,
            confirmation_token=request.confirmation_token,
        )

        audit.record_event(
            event_type="POLICY_CHECKED",
            action=request.tool_name,
            risk_level=risk_level,
            status=decision.decision.value,
            details={"correlation_id": corr_id, "reason": decision.reason},
        )

        if decision.is_denied:
            return ToolResult(
                status="DENIED",
                message=f"Policy denied execution of '{request.tool_name}': {decision.reason}",
                error="PolicyDenied",
            )

        if decision.is_need_confirm:
            audit.record_event(
                event_type="CONFIRMATION_REQUIRED",
                action=request.tool_name,
                risk_level=risk_level,
                status="PENDING_CONFIRMATION",
                details={"correlation_id": corr_id, "token": decision.token},
            )
            return ToolResult(
                status="NEED_CONFIRM",
                message=decision.summary,
                data={
                    "token": decision.token,
                    "risk_level": risk_level,
                    "summary": decision.summary,
                    "details": decision.details,
                    "correlation_id": corr_id,
                },
            )

        # 6. Execution with Timeout & Bounded Fallback
        timeout_s = request.timeout_s if request.timeout_s > 0 else tool.timeout_s
        raw_result = None
        exec_error = None
        fallback_used = False

        def _execute_call(fn: Callable[..., Any], args: dict[str, Any]) -> Any:
            return fn(**args)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_execute_call, tool.handler, request.arguments)
            try:
                raw_result = future.result(timeout=timeout_s)
                audit.record_event(
                    event_type="TASK_EXECUTED",
                    action=request.tool_name,
                    risk_level=risk_level,
                    status="SUCCESS",
                    details={"correlation_id": corr_id},
                )
            except concurrent.futures.TimeoutError:
                audit.record_event(
                    event_type="TASK_TIMEOUT",
                    action=request.tool_name,
                    risk_level=risk_level,
                    status="TIMEOUT",
                    details={"correlation_id": corr_id, "timeout_s": timeout_s},
                )
                return ToolResult(
                    status="TIMEOUT",
                    message=f"Execution of '{request.tool_name}' exceeded timeout of {timeout_s}s.",
                    error="TimeoutError",
                )
            except Exception as exc:
                exec_error = str(exc)
                logger.warning("Primary execution failed for %s: %s", request.tool_name, exc)

        # Re-check Kill Switch post-execution
        if kill_switch.is_active:
            return ToolResult(
                status="CANCELLED",
                message="Operation cancelled by emergency kill switch during or after execution.",
                error="KillSwitchEngaged",
            )

        # Fallback handling (strictly bounded to safe operations, Risk <= 1)
        if exec_error and risk_level <= 1 and request.tool_name in self._fallback_handlers:
            fallback_fn = self._fallback_handlers[request.tool_name]
            audit.record_event(
                event_type="TASK_FALLBACK_ATTEMPT",
                action=request.tool_name,
                risk_level=risk_level,
                status="FALLBACK",
                details={"correlation_id": corr_id, "primary_error": exec_error},
            )
            try:
                raw_result = fallback_fn(**request.arguments)
                fallback_used = True
                exec_error = None
            except Exception as fb_exc:
                exec_error = f"Primary failed ({exec_error}); fallback also failed: {fb_exc}"

        if exec_error:
            audit.record_event(
                event_type="TASK_EXECUTION_FAILED",
                action=request.tool_name,
                risk_level=risk_level,
                status="FAILED",
                details={"correlation_id": corr_id, "error": exec_error},
            )
            return ToolResult(
                status="FAILED",
                message=f"Execution failed for '{request.tool_name}': {exec_error}",
                error=exec_error,
            )

        # 7. Post-Execution Verification
        audit.record_event(
            event_type="VERIFICATION_STARTED",
            action=request.tool_name,
            risk_level=risk_level,
            status="VERIFYING",
            details={"correlation_id": corr_id},
        )

        verifier = self.verifier_registry.get_verifier(request.tool_name)
        verif_result = verifier.verify(request.tool_name, request.arguments, raw_result)

        audit.record_event(
            event_type="VERIFICATION_COMPLETED",
            action=request.tool_name,
            risk_level=risk_level,
            status=verif_result.status,
            details={
                "correlation_id": corr_id,
                "evidence": verif_result.evidence,
                "message": verif_result.message,
            },
        )

        # 8. Report Final Typed Result
        output_msg = raw_result.message if hasattr(raw_result, "message") else str(raw_result)
        final_message = verif_result.message or output_msg
        result_data = {
            "raw_result": output_msg,
            "fallback_used": fallback_used,
            "correlation_id": corr_id,
        }
        if hasattr(raw_result, "data") and isinstance(raw_result.data, dict):
            result_data.update(raw_result.data)

        final_tool_res = ToolResult(
            status=verif_result.status,
            message=final_message,
            data=result_data,
            evidence=verif_result.evidence,
        )

        audit.record_event(
            event_type="TASK_COMPLETED",
            action=request.tool_name,
            risk_level=risk_level,
            status=verif_result.status,
            details={"correlation_id": corr_id},
        )

        return final_tool_res


_global_execution_engine: Optional[ExecutionEngine] = None


def get_execution_engine() -> ExecutionEngine:
    """Return the central singleton ExecutionEngine."""
    global _global_execution_engine
    if _global_execution_engine is None:
        _global_execution_engine = ExecutionEngine()
    return _global_execution_engine
