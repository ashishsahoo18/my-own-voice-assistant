"""Strict plan validation against schemas, step limits, and security constraints."""

from __future__ import annotations

from typing import Optional
from agent.models import Plan, PlanStep
from core.config import get_config
from core.logging import get_logger
from skills.registry import SkillRegistry, get_skill_registry

logger = get_logger("agent.validator")


class PlanValidationError(Exception):
    """Raised when a proposed plan violates security or schema constraints."""


class PlanValidator:
    """Enforces schema validity, bounded step counts, and policy compliance on agent plans."""

    def __init__(self, registry: Optional[SkillRegistry] = None) -> None:
        self.registry = registry or get_skill_registry()
        self.config = get_config()
        self.max_steps = self.config.agent.max_plan_steps  # Hard bound: 6

    def validate(self, plan: Plan) -> tuple[bool, list[str]]:
        """Validate a plan against strict structural, bounds, and safety requirements.

        Returns:
            (is_valid, list_of_error_reasons)
        """
        errors: list[str] = []

        if not plan.goal or not plan.goal.strip():
            errors.append("Plan goal cannot be empty.")

        if not plan.steps:
            errors.append("Plan must contain at least one step.")

        if len(plan.steps) > self.max_steps:
            errors.append(
                f"Plan step count ({len(plan.steps)}) exceeds maximum allowed limit ({self.max_steps})."
            )

        expected_step_num = 1
        for step in plan.steps:
            # 1. Sequential numbering
            if step.step_number != expected_step_num:
                errors.append(
                    f"Step numbering sequence broken: expected step {expected_step_num}, got {step.step_number}."
                )
            expected_step_num += 1

            # 2. Tool existence
            if not step.tool_name or not step.tool_name.strip():
                errors.append(f"Step {step.step_number} has an empty tool_name.")
                continue

            tool = self.registry.get_tool(step.tool_name)
            if tool is None:
                errors.append(
                    f"Step {step.step_number} requests unknown/unregistered tool '{step.tool_name}'."
                )
                continue

            # 3. Arguments dictionary type check
            if not isinstance(step.arguments, dict):
                errors.append(
                    f"Step {step.step_number} arguments must be a dictionary, got {type(step.arguments).__name__}."
                )
                continue

            # 4. Security bypass prevention
            # Check for forbidden self-granting or privilege escalation payloads
            for key, val in step.arguments.items():
                if isinstance(val, str):
                    lowered = val.lower()
                    if any(bad in lowered for bad in ("--bypass-policy", "__override_auth__", "sudo", "chmod 777")):
                        errors.append(
                            f"Step {step.step_number} contains suspicious security bypass token in argument '{key}'."
                        )

            # 5. Populate confirmation metadata from registered tool
            step.requires_confirmation = tool.requires_confirmation

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning("Plan validation failed for '%s': %s", plan.goal, errors)
        return is_valid, errors

    def validate_or_raise(self, plan: Plan) -> None:
        """Validate plan or raise PlanValidationError with combined error messages."""
        is_valid, errors = self.validate(plan)
        if not is_valid:
            raise PlanValidationError("; ".join(errors))
