"""Comprehensive regression tests for Phase 6: Multi-Step Agentic Task Loop and Planner."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
import unittest

from agent.executor import AgentTaskLoop
from agent.loop_detector import LoopDetectedError, LoopDetector
from agent.models import Plan, PlanStep, StepResult, TaskReport
from agent.persistence import TaskStore
from agent.planner import Planner
from agent.validator import PlanValidationError, PlanValidator
from core.config import get_config, reload_config
from execution.engine import ExecutionEngine
from memory.manager import HybridMemoryEngine
from memory.unified_db import UnifiedDatabase
from security.confirmation import ConfirmationManager
from security.kill_switch import KillSwitch
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec
from skills.registry import SkillRegistry


class MockDummySkill(BaseSkill):
    """Mock test skill for exercising multi-step agent behaviors safely."""

    def __init__(self) -> None:
        super().__init__()
        self.call_log: list[tuple[str, dict]] = []
        self.should_fail_step: set[str] = set()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="testmock",
            version="1.0.0",
            description="Mock testing skill",
            triggers=["mock"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="testmock.step_a",
                description="Step A action",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.step_a,
            ),
            ToolSpec(
                name="testmock.step_b",
                description="Step B action",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.step_b,
            ),
            ToolSpec(
                name="testmock.sensitive_action",
                description="Action requiring confirmation",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.sensitive_action,
            ),
            ToolSpec(
                name="testmock.destructive_action",
                description="Destructive action",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.destructive_action,
            ),
        ]

    def step_a(self, item: str = "default") -> ToolResult:
        self.call_log.append(("step_a", {"item": item}))
        if "step_a" in self.should_fail_step:
            return ToolResult(status="FAILED", message="Step A intentional failure", error="MockFailure")
        return ToolResult(status="SUCCESS", message=f"Step A executed with {item}", data={"created_file": item})

    def step_b(self, item: str = "default") -> ToolResult:
        self.call_log.append(("step_b", {"item": item}))
        if "step_b" in self.should_fail_step:
            return ToolResult(status="FAILED", message="Step B intentional failure", error="MockFailure")
        return ToolResult(status="SUCCESS", message=f"Step B executed with {item}")

    def sensitive_action(self, target: str = "") -> ToolResult:
        self.call_log.append(("sensitive_action", {"target": target}))
        return ToolResult(status="SUCCESS", message=f"Sensitive action executed on {target}")

    def destructive_action(self, target: str = "") -> ToolResult:
        self.call_log.append(("destructive_action", {"target": target}))
        return ToolResult(status="SUCCESS", message=f"Destructive action executed on {target}")


class MockLLM:
    """Deterministic offline LLM for agent testing."""

    def __init__(self, plan_to_return=None) -> None:
        self.plan_to_return = plan_to_return

    def structured_output(self, prompt, schema, system_prompt=None, max_retries=1):
        return self.plan_to_return

    def check_health(self):
        return True, "http://mock:11434", "mock_model", ["mock_model"], "Mock active"


class TestAgentTaskLoop(unittest.TestCase):
    """Test suite for bounded multi-step agent planner and task loop."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_agent.db"
        self.db = UnifiedDatabase(self.db_path)

        # Isolated skill registry with mock skill
        self.registry = SkillRegistry()
        self.mock_skill = MockDummySkill()
        self.registry.register(self.mock_skill)

        # Isolated memory engine
        self.memory = HybridMemoryEngine(db=self.db)

        # Isolated store
        self.store = TaskStore(db=self.db)

        # Security and engine components
        self.kill_switch = KillSwitch()
        self.confirmation_mgr = ConfirmationManager()
        self.execution_engine = ExecutionEngine(registry=self.registry)

        # Mock LLM and Planner
        self.mock_llm = MockLLM()
        self.validator = PlanValidator(registry=self.registry)
        self.planner = Planner(
            llm=self.mock_llm,
            registry=self.registry,
            memory=self.memory,
            validator=self.validator,
        )
        self.loop_detector = LoopDetector()

        # Task loop under test
        self.task_loop = AgentTaskLoop(
            engine=self.execution_engine,
            planner=self.planner,
            validator=self.validator,
            loop_detector=self.loop_detector,
            store=self.store,
            memory=self.memory,
            kill_switch=self.kill_switch,
            confirmation_mgr=self.confirmation_mgr,
        )

    def tearDown(self) -> None:
        self.db.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_valid_plan_execution(self) -> None:
        """Verify sequential execution and verification of a valid 2-step plan."""
        plan = Plan(
            goal="Execute steps A and B",
            steps=[
                PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "report.docx"}),
                PlanStep(step_number=2, tool_name="testmock.step_b", arguments={"item": "finished"}),
            ],
        )

        report = self.task_loop.run(goal=plan.goal, plan_override=plan)
        self.assertEqual(report.overall_status, "SUCCESS")
        self.assertTrue(report.is_success)
        self.assertEqual(len(report.steps_executed), 2)
        self.assertEqual(len(self.mock_skill.call_log), 2)
        self.assertIn("Step A executed with report.docx", report.summary)
        self.assertIn("Step B executed with finished", report.summary)

    def test_step_limits_exceeded(self) -> None:
        """Verify plans exceeding max 6 steps are rejected by PlanValidator."""
        steps = [
            PlanStep(step_number=i, tool_name="testmock.step_a", arguments={"item": f"item_{i}"})
            for i in range(1, 8)  # 7 steps
        ]
        oversized_plan = Plan(goal="Oversized goal", steps=steps)

        is_valid, errors = self.validator.validate(oversized_plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("exceeds maximum allowed limit" in err for err in errors))

        # Task loop must reject plan and not execute any step
        report = self.task_loop.run(goal=oversized_plan.goal, plan_override=oversized_plan)
        self.assertEqual(report.overall_status, "FAILED")
        self.assertIn("Plan validation failed", report.summary)
        self.assertEqual(len(self.mock_skill.call_log), 0)

    def test_invalid_plan_unknown_tool(self) -> None:
        """Verify plan requesting unregistered tool is safely rejected."""
        invalid_plan = Plan(
            goal="Do something with phantom tool",
            steps=[
                PlanStep(step_number=1, tool_name="phantom.nonexistent_tool", arguments={}),
            ],
        )
        is_valid, errors = self.validator.validate(invalid_plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("unknown/unregistered tool" in err for err in errors))

        report = self.task_loop.run(goal=invalid_plan.goal, plan_override=invalid_plan)
        self.assertEqual(report.overall_status, "FAILED")
        self.assertIn("Plan validation failed", report.summary)

    def test_policy_bypass_attempt(self) -> None:
        """Verify plans containing privilege escalation tokens are rejected."""
        bypass_plan = Plan(
            goal="Sneak bypass into arguments",
            steps=[
                PlanStep(
                    step_number=1,
                    tool_name="testmock.step_a",
                    arguments={"item": "report.txt --bypass-policy"},
                ),
            ],
        )
        is_valid, errors = self.validator.validate(bypass_plan)
        self.assertFalse(is_valid)
        self.assertTrue(any("suspicious security bypass" in err for err in errors))

        report = self.task_loop.run(goal=bypass_plan.goal, plan_override=bypass_plan)
        self.assertEqual(report.overall_status, "FAILED")
        self.assertEqual(len(self.mock_skill.call_log), 0)

    def test_confirmation_enforcement(self) -> None:
        """Verify actions requiring confirmation pause safely unless explicitly confirmed."""
        plan = Plan(
            goal="Perform sensitive action",
            steps=[
                PlanStep(
                    step_number=1,
                    tool_name="testmock.sensitive_action",
                    arguments={"target": "config_database"},
                    requires_confirmation=True,
                ),
            ],
        )

        # 1. Unconfirmed run: must pause in WAITING_CONFIRMATION
        report = self.task_loop.run(goal=plan.goal, plan_override=plan, user_confirmed=False)
        self.assertEqual(report.overall_status, "WAITING_CONFIRMATION")
        self.assertEqual(len(self.mock_skill.call_log), 0)  # Action was NOT executed

        # 2. Confirmed run: must execute cleanly
        report_confirmed = self.task_loop.run(goal=plan.goal, plan_override=plan, user_confirmed=True)
        self.assertEqual(report_confirmed.overall_status, "SUCCESS")
        self.assertEqual(len(self.mock_skill.call_log), 1)

    def test_failed_step_halts_subsequent_steps(self) -> None:
        """Verify failure in step 1 stops execution and does not blindly execute step 2."""
        self.mock_skill.should_fail_step.add("step_a")
        plan = Plan(
            goal="Execute steps A and B",
            steps=[
                PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "data"}),
                PlanStep(step_number=2, tool_name="testmock.step_b", arguments={"item": "data"}),
            ],
        )

        report = self.task_loop.run(goal=plan.goal, plan_override=plan)
        self.assertIn(report.overall_status, ("FAILED", "REPLAN_EXHAUSTED"))
        # Step B must NOT have been called
        called_tools = [c[0] for c in self.mock_skill.call_log]
        self.assertIn("step_a", called_tools)
        self.assertNotIn("step_b", called_tools)

    def test_loop_detection_immediate_duplicate(self) -> None:
        """Verify loop detector blocks immediate identical action repeats."""
        plan = Plan(
            goal="Repeat step identically",
            steps=[
                PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "same_arg"}),
                PlanStep(step_number=2, tool_name="testmock.step_a", arguments={"item": "same_arg"}),
            ],
        )

        report = self.task_loop.run(goal=plan.goal, plan_override=plan)
        self.assertEqual(report.overall_status, "FAILED")
        self.assertIn("Immediate duplicate action detected", report.summary)
        # Only the first call executed; second was blocked by loop detector
        self.assertEqual(len(self.mock_skill.call_log), 1)

    def test_loop_detection_repeated_destructive_action(self) -> None:
        """Verify repeated destructive actions in the same task are blocked."""
        loop_detector = LoopDetector()
        # Direct detector check for destructive tool
        loop_detector.DESTRUCTIVE_TOOLS.add("testmock.destructive_action")

        is_loop, _ = loop_detector.check_and_record("testmock.destructive_action", {"target": "file1.txt"})
        self.assertFalse(is_loop)

        # Second destructive action in same task must be blocked
        is_loop2, reason2 = loop_detector.check_and_record("testmock.destructive_action", {"target": "file2.txt"})
        self.assertTrue(is_loop2)
        self.assertIn("Repeated destructive action blocked", reason2)

    def test_cancellation_and_kill_switch(self) -> None:
        """Verify kill switch immediately aborts task execution."""
        self.kill_switch.activate(reason="Emergency Stop Activated")
        plan = Plan(
            goal="Execute under kill switch",
            steps=[
                PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "data"}),
            ],
        )

        report = self.task_loop.run(goal=plan.goal, plan_override=plan)
        self.assertEqual(report.overall_status, "CANCELLED")
        self.assertEqual(len(self.mock_skill.call_log), 0)

    def test_persistence_and_resume_prevents_duplicate_actions(self) -> None:
        """Verify interrupted tasks can be resumed without re-executing verified steps."""
        plan = Plan(
            goal="Two step pipeline",
            steps=[
                PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "first_item"}),
                PlanStep(step_number=2, tool_name="testmock.sensitive_action", arguments={"target": "second_target"}, requires_confirmation=True),
            ],
        )
        task_id = "task_persist_01"

        # Run unconfirmed: Step 1 succeeds, Step 2 pauses waiting confirmation
        rep1 = self.task_loop.run(goal=plan.goal, task_id=task_id, plan_override=plan, user_confirmed=False)
        self.assertEqual(rep1.overall_status, "WAITING_CONFIRMATION")
        self.assertEqual(len(self.mock_skill.call_log), 1)  # Only Step 1 was executed

        # Verify task is recorded in SQLite store
        stored_task = self.store.get_task(task_id)
        self.assertIsNotNone(stored_task)
        self.assertEqual(stored_task["status"], "WAITING_CONFIRMATION")

        completed_steps = self.store.get_task_steps(task_id)
        self.assertGreaterEqual(len(completed_steps), 1)

        # Resume with confirmation: Step 1 must NOT be re-executed, only Step 2 executes!
        rep2 = self.task_loop.resume(task_id=task_id, user_confirmed=True)
        self.assertEqual(rep2.overall_status, "SUCCESS")
        # Total calls should now be 2 (Step 1 was executed once in rep1, Step 2 executed once in rep2)
        self.assertEqual(len(self.mock_skill.call_log), 2)
        self.assertEqual(self.mock_skill.call_log[0][0], "step_a")
        self.assertEqual(self.mock_skill.call_log[1][0], "sensitive_action")

    def test_honest_reporting_includes_verification_evidence(self) -> None:
        """Verify TaskReport summary strictly contains real step evidence and verifier badges."""
        plan = Plan(
            goal="Inspect honesty",
            steps=[
                PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "honest_file.txt"}),
            ],
        )
        report = self.task_loop.run(goal=plan.goal, plan_override=plan)
        self.assertIn("[VERIFIED]", report.summary)
        self.assertIn("honest_file.txt", report.summary)
        self.assertFalse(report.summary.startswith("Everything worked perfectly because AI said so"))

    def test_memory_integration_read_only(self) -> None:
        """Verify planner reads from memory without automatically persisting tasks as permanent facts."""
        self.memory.remember("User preferred item is custom_item", category="preferences")
        initial_count = self.memory.semantic.count()

        # Planner recalls context
        memories = self.memory.recall("item")
        self.assertGreaterEqual(len(memories), 1)

        # Execute task
        plan = Plan(
            goal="Task with memory context",
            steps=[PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "read_context"})],
        )
        self.task_loop.run(goal=plan.goal, plan_override=plan)

        # Memory store count must NOT have increased (task was not saved as a permanent user fact)
        self.assertEqual(self.memory.semantic.count(), initial_count)

    def test_replanning_limit_bounded_to_one(self) -> None:
        """Verify replanning occurs at most once and halts if recovery also fails."""
        from agent.planner import PlanSchema, StepSchema

        self.mock_skill.should_fail_step.add("step_a")
        # LLM returns alternative plan using step_b (which also fails)
        self.mock_skill.should_fail_step.add("step_b")
        self.mock_llm.plan_to_return = PlanSchema(
            goal="Alternative goal",
            steps=[StepSchema(step_number=1, tool_name="testmock.step_b", arguments={"item": "alt"})],
        )

        plan = Plan(
            goal="Try step A",
            steps=[PlanStep(step_number=1, tool_name="testmock.step_a", arguments={"item": "primary"})],
        )

        report = self.task_loop.run(goal=plan.goal, plan_override=plan)
        # Should be REPLAN_EXHAUSTED because it replanned once, and second attempt also failed
        self.assertEqual(report.overall_status, "REPLAN_EXHAUSTED")
        self.assertEqual(report.replan_count, 1)


if __name__ == "__main__":
    unittest.main()
