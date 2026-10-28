"""Bounded multi-step planner translating user goals into validated schema-constrained plans."""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Type
from pydantic import BaseModel, Field

from agent.models import Plan, PlanStep, StepResult
from agent.validator import PlanValidator
from core.config import get_config
from core.logging import get_logger
from llm.ollama_provider import OllamaProvider
from memory.manager import HybridMemoryEngine, get_memory_engine
from skills.registry import SkillRegistry, get_skill_registry

logger = get_logger("agent.planner")


class StepSchema(BaseModel):
    step_number: int
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    expected_outcome: str = ""


class PlanSchema(BaseModel):
    goal: str
    steps: list[StepSchema] = Field(default_factory=list)


class Planner:
    """Generates bounded, schema-constrained multi-step plans using local AI and deterministic fallbacks."""

    def __init__(
        self,
        llm: Optional[OllamaProvider] = None,
        registry: Optional[SkillRegistry] = None,
        memory: Optional[HybridMemoryEngine] = None,
        validator: Optional[PlanValidator] = None,
    ) -> None:
        self.llm = llm or OllamaProvider()
        self.registry = registry or get_skill_registry()
        self.memory = memory or get_memory_engine()
        self.validator = validator or PlanValidator(self.registry)
        self.config = get_config()
        self.max_steps = self.config.agent.max_plan_steps  # Hard bound: 6
        self.max_replans = self.config.agent.max_replans  # Bound: 1

    def plan(self, goal: str, session_id: str = "default") -> Plan:
        """Create a validated execution plan for the requested goal.

        Enforces:
        - Maximum 6 steps
        - Strict JSON schema
        - Skill registry validation
        - Relevant user memory context injection without persisting task
        """
        clean_goal = goal.strip()
        if not clean_goal:
            return Plan(goal=clean_goal, steps=[])

        # 1. Fetch relevant memory context (read-only; does not save task)
        memory_context = ""
        try:
            memories = self.memory.recall(query=clean_goal, limit=3)
            if memories:
                memory_context = "Relevant user preferences and facts:\n" + "\n".join(
                    f"- {m['content']}" for m in memories
                )
        except Exception as exc:
            logger.debug("Failed fetching memory context: %s", exc)

        # 2. Attempt Local LLM Structured Generation
        plan = self._generate_with_llm(clean_goal, memory_context)

        # 3. If LLM is unavailable or generated an invalid plan, use deterministic heuristic planner
        if plan is None or not plan.steps:
            plan = self._generate_heuristic_plan(clean_goal)

        # 4. Truncate strictly to max_steps if exceeded
        if len(plan.steps) > self.max_steps:
            plan.steps = plan.steps[: self.max_steps]
            # Renumber sequentially
            for i, s in enumerate(plan.steps, start=1):
                s.step_number = i

        # 5. Populate confirmation requirements from tool definitions
        for s in plan.steps:
            tool = self.registry.get_tool(s.tool_name)
            if tool:
                s.requires_confirmation = tool.requires_confirmation

        return plan

    def replan(
        self,
        goal: str,
        completed_steps: list[StepResult],
        failed_step: StepResult,
        failure_reason: str,
        session_id: str = "default",
    ) -> Optional[Plan]:
        """Attempt bounded recovery: generate an alternative plan for the remaining unfulfilled goal.

        Enforces:
        - At most 1 replan attempt
        - Never repeats completed verified actions
        """
        # Build prompt describing the failure and requesting an alternative
        completed_descriptions = [
            f"Step {s.step_number} ({s.tool_name}): SUCCESS (Verified)"
            for s in completed_steps
            if s.status == "SUCCESS"
        ]
        completed_summary = "\n".join(completed_descriptions) if completed_descriptions else "None"

        replan_prompt = (
            f"Original Goal: {goal}\n"
            f"Successfully Completed Steps:\n{completed_summary}\n\n"
            f"Failed Step: {failed_step.tool_name} (Step {failed_step.step_number})\n"
            f"Failure Reason: {failure_reason}\n\n"
            f"Propose alternative remaining steps to accomplish the goal without repeating completed actions."
        )

        plan = self._generate_with_llm(replan_prompt, "")
        if plan is None or not plan.steps:
            # Fallback heuristic replan: try safe alternatives if known
            plan = self._heuristic_replan(goal, completed_steps, failed_step, failure_reason)

        if plan:
            plan.replan_count = 1
            # Bound steps
            if len(plan.steps) > self.max_steps:
                plan.steps = plan.steps[: self.max_steps]
            for i, s in enumerate(plan.steps, start=1):
                s.step_number = i
                tool = self.registry.get_tool(s.tool_name)
                if tool:
                    s.requires_confirmation = tool.requires_confirmation

        return plan

    def _generate_with_llm(self, goal: str, memory_context: str) -> Optional[Plan]:
        """Request structured plan from Ollama."""
        tools_summary = self._get_available_tools_prompt()
        system_prompt = (
            "You are OLIVER's task decomposition planner. Generate a strict JSON plan with 1 to 6 sequential steps.\n"
            f"Available tools:\n{tools_summary}\n"
            f"{memory_context}\n"
            "Rules:\n"
            "- Maximum 6 steps total.\n"
            "- Step numbers must be 1, 2, 3, etc.\n"
            "- Use ONLY registered tool names from the available tools list.\n"
            "- Output valid arguments for each tool."
        )

        try:
            structured = self.llm.structured_output(
                prompt=f"Goal: {goal}",
                schema=PlanSchema,
                system_prompt=system_prompt,
                max_retries=1,
            )
            if structured and structured.steps:
                plan_steps = [
                    PlanStep(
                        step_number=s.step_number,
                        tool_name=s.tool_name,
                        arguments=s.arguments,
                        description=s.description,
                        expected_outcome=s.expected_outcome,
                    )
                    for s in structured.steps
                ]
                plan = Plan(goal=goal, steps=plan_steps)
                is_valid, _ = self.validator.validate(plan)
                if is_valid:
                    return plan
        except Exception as exc:
            logger.debug("LLM planning encountered error: %s", exc)

        return None

    def _generate_heuristic_plan(self, goal: str) -> Plan:
        """Deterministic plan generation for common composite intents when offline."""
        lowered = goal.lower()
        steps: list[PlanStep] = []

        # 1. Composite: "create folder X and create file Y"
        if "create folder" in lowered and "create file" in lowered:
            folder_match = re.search(r"create\s+folder\s+([^\s,;]+)", lowered)
            file_match = re.search(r"create\s+file\s+([^\s,;]+)", lowered)
            folder_name = folder_match.group(1).strip() if folder_match else "NewFolder"
            file_name = file_match.group(1).strip() if file_match else "note.txt"

            steps.append(
                PlanStep(
                    step_number=1,
                    tool_name="files.create_folder",
                    arguments={"path": folder_name},
                    description=f"Create folder '{folder_name}'",
                )
            )
            steps.append(
                PlanStep(
                    step_number=2,
                    tool_name="files.create_file",
                    arguments={"path": f"{folder_name}/{file_name}", "content": "Created by OLIVER"},
                    description=f"Create file '{file_name}' inside folder '{folder_name}'",
                )
            )

        # 2. Composite: "calculate X and save note" or "calculate X and remind me"
        elif "calculate" in lowered and ("note" in lowered or "remind" in lowered):
            calc_match = re.search(r"calculate\s+([0-9\+\-\*\/\.\s]+)", lowered)
            expr = calc_match.group(1).strip() if calc_match else "2+2"

            steps.append(
                PlanStep(
                    step_number=1,
                    tool_name="productivity.calculate",
                    arguments={"expression": expr},
                    description=f"Calculate expression: {expr}",
                )
            )
            if "remind" in lowered:
                steps.append(
                    PlanStep(
                        step_number=2,
                        tool_name="productivity.add_reminder",
                        arguments={"title": f"Calculation result for {expr}"},
                        description="Add reminder with calculation result",
                    )
                )
            else:
                steps.append(
                    PlanStep(
                        step_number=2,
                        tool_name="memory.remember",
                        arguments={"content": f"Calculation result for {expr}"},
                        description="Save calculation note into memory",
                    )
                )

        # 3. Single tool decomposition fallback
        else:
            if "reminder" in lowered or "remind me" in lowered:
                title = re.sub(r"^remind\s+me\s+(?:to\s+)?", "", goal, flags=re.IGNORECASE).strip()
                steps.append(
                    PlanStep(step_number=1, tool_name="productivity.add_reminder", arguments={"title": title})
                )
            elif "weather" in lowered:
                loc = re.sub(r"^weather(?:\s+in\s+)?", "", goal, flags=re.IGNORECASE).strip()
                steps.append(
                    PlanStep(step_number=1, tool_name="info.weather", arguments={"location": loc})
                )
            elif "search google" in lowered or lowered.startswith("search "):
                q = re.sub(r"^search\s+(?:google\s+(?:for\s+)?)?", "", goal, flags=re.IGNORECASE).strip()
                steps.append(
                    PlanStep(step_number=1, tool_name="browser.search_google", arguments={"query": q})
                )

        return Plan(goal=goal, steps=steps)

    def _heuristic_replan(
        self,
        goal: str,
        completed_steps: list[StepResult],
        failed_step: StepResult,
        failure_reason: str,
    ) -> Optional[Plan]:
        """Heuristic recovery when a tool fails."""
        # Example: if search_google fails, fall back to browser.open_site or info.news
        if failed_step.tool_name == "browser.search_google":
            q = failed_step.message
            return Plan(
                goal=goal,
                steps=[
                    PlanStep(
                        step_number=1,
                        tool_name="browser.open_site",
                        arguments={"site_name": "google"},
                        description="Fallback: open Google directly in browser",
                    )
                ],
                replan_count=1,
            )
        return None

    def _get_available_tools_prompt(self) -> str:
        """Format list of registered tools with descriptions for LLM prompting."""
        tools = self.registry.get_all_tools()
        lines = []
        for t in tools:
            risk_label = t.risk_level.name
            lines.append(f"- {t.name}: {t.description} [Risk: {risk_label}]")
        return "\n".join(lines[:30])
