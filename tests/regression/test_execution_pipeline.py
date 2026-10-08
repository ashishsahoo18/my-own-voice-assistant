"""Regression tests for OLIVER 2.0 Central Execution and Verification Pipeline (Phase 4)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.logging import get_audit_logger
from execution.engine import ExecutionEngine, get_execution_engine
from execution.request import TaskRequest
from execution.verifiers import (
    CommunicationVerifier,
    FileVerifier,
    ProcessVerifier,
    VerifierRegistry,
)
from security.confirmation import ConfirmationManager
from security.kill_switch import KillSwitch
from security.policy_engine import PolicyEngine
from security.sandbox import PathSandbox
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec
from skills.registry import SkillRegistry


class ExecutionPipelineTests(unittest.TestCase):
    """Unit and regression tests for Phase 4 ExecutionEngine and Verifiers."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.sandbox = PathSandbox(allowed_roots=[self.tmp_path])
        self.confirm_mgr = ConfirmationManager(default_timeout_s=5.0)
        self.kill_switch = KillSwitch()
        self.policy_engine = PolicyEngine(
            sandbox=self.sandbox,
            confirmation_manager=self.confirm_mgr,
            kill_switch=self.kill_switch,
        )

        self.registry = SkillRegistry()

        # Register test skill with diverse risk levels and behaviors
        class PipelineTestSkill(BaseSkill):
            def __init__(self, tmp_root: Path) -> None:
                super().__init__()
                self.tmp_root = tmp_root

            def get_manifest(self) -> SkillManifest:
                return SkillManifest(name="pipeline_test", description="Pipeline testing skill")

            def get_tools(self) -> list[ToolSpec]:
                return [
                    ToolSpec(
                        name="pipeline_test.create_file",
                        description="Create a test file",
                        risk_level=ToolRiskLevel.LOW,
                        handler=self._create_file,
                    ),
                    ToolSpec(
                        name="pipeline_test.create_failing_file",
                        description="Tool that claims success but fails to create file",
                        risk_level=ToolRiskLevel.LOW,
                        handler=self._fake_create_file,
                    ),
                    ToolSpec(
                        name="pipeline_test.slow_operation",
                        description="Operation that exceeds timeout",
                        risk_level=ToolRiskLevel.LOW,
                        handler=self._slow_op,
                    ),
                    ToolSpec(
                        name="pipeline_test.flaky_action",
                        description="Fails initially to test fallback",
                        risk_level=ToolRiskLevel.LOW,
                        handler=self._flaky_op,
                    ),
                    ToolSpec(
                        name="pipeline_test.sensitive_message",
                        description="Sensitive WhatsApp dispatch",
                        risk_level=ToolRiskLevel.SENSITIVE,
                        requires_confirmation=True,
                        handler=lambda message="": f"Dispatched: {message}",
                    ),
                ]

            def _create_file(self, filename: str = "", content: str = "test", path: str = "", **kwargs: Any) -> str:
                target = Path(path) if path else (self.tmp_root / filename)
                target.write_text(content, encoding="utf-8")
                return f"Created {target.name}"

            def _fake_create_file(self, filename: str = "", path: str = "", **kwargs: Any) -> str:
                # Intentionally does NOT create the file to trigger verification failure
                return f"Created {filename}"

            def _slow_op(self) -> str:
                time.sleep(1.0)
                return "Completed late"

            def _flaky_op(self) -> str:
                raise RuntimeError("Primary execution failed unexpectedly")

        self.test_skill = PipelineTestSkill(self.tmp_path)
        self.registry.register(self.test_skill)

        self.engine = ExecutionEngine()

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    # --- 1. File Verification: Verified vs Failed Creation ---

    def test_successful_verified_file_creation(self) -> None:
        """Verifier confirms created file exists, is a file, and captures size evidence."""
        req = TaskRequest(
            tool_name="pipeline_test.create_file",
            arguments={"filename": "doc.txt", "path": str(self.tmp_path / "doc.txt")},
        )
        # Point registry lookup in engine to our test registry for this test
        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            result = self.engine.execute(req)

        self.assertEqual(result.status, "VERIFIED")
        self.assertTrue(result.is_success)
        self.assertIn("exists", result.evidence)
        self.assertTrue(result.evidence["exists"])
        self.assertEqual(result.evidence["size_bytes"], 4)

    def test_failed_file_creation_verification(self) -> None:
        """Tool reports success but verifier detects file was not created, marking FAILED."""
        req = TaskRequest(
            tool_name="pipeline_test.create_failing_file",
            arguments={"filename": "phantom.txt", "path": str(self.tmp_path / "phantom.txt")},
        )
        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            result = self.engine.execute(req)

        self.assertEqual(result.status, "FAILED")
        self.assertFalse(result.is_success)
        self.assertFalse(result.evidence.get("exists", True))

    # --- 2. Move / Rename / Delete Verifiers ---

    def test_file_verifier_rename_and_move(self) -> None:
        file_ver = FileVerifier()
        src = self.tmp_path / "old.txt"
        dst = self.tmp_path / "new.txt"
        dst.write_text("content", encoding="utf-8")

        # Destination exists and source absent
        res = file_ver.verify("files.rename_file", {"path": str(src), "new_path": str(dst)}, "Renamed")
        self.assertEqual(res.status, "VERIFIED")
        self.assertTrue(res.evidence["destination_exists"])
        self.assertTrue(res.evidence["source_absent"])

    def test_file_verifier_deletion_verification(self) -> None:
        file_ver = FileVerifier()
        deleted_file = self.tmp_path / "deleted.txt"
        # File does not exist on disk
        res = file_ver.verify("files.delete_file", {"path": str(deleted_file)}, "Deleted")
        self.assertEqual(res.status, "VERIFIED")
        self.assertTrue(res.evidence["absent_from_target"])

        # If file still exists on disk, delete verifier must fail
        still_there = self.tmp_path / "persisting.txt"
        still_there.write_text("data", encoding="utf-8")
        res_fail = file_ver.verify("files.delete_file", {"path": str(still_there)}, "Deleted")
        self.assertEqual(res_fail.status, "FAILED")
        self.assertTrue(res_fail.evidence["still_exists"])

    # --- 3. Process Verification ---

    def test_process_verifier_running_process(self) -> None:
        proc_ver = ProcessVerifier()
        # Mock psutil to return a matching process
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 4321, "name": "notepad.exe"}

        with patch("psutil.process_iter", return_value=[mock_proc]):
            res = proc_ver.verify("windows.open_app", {"app_name": "notepad"}, "Opened notepad.")
            self.assertEqual(res.status, "VERIFIED")
            self.assertTrue(res.evidence["process_found"])
            self.assertEqual(res.evidence["processes"][0]["pid"], 4321)

    # --- 4. Honest UNVERIFIED Result on Communications ---

    def test_communication_verifier_unverified_honesty(self) -> None:
        """Communication verification returns UNVERIFIED; never claims unverified delivery."""
        comm_ver = CommunicationVerifier()
        res = comm_ver.verify("communication.whatsapp_send", {"phone": "+12345", "message": "Hi"}, "Sent")
        self.assertEqual(res.status, "UNVERIFIED")
        self.assertFalse(res.evidence["delivery_receipt_supported"])

    # --- 5. Policy Denied Result ---

    def test_policy_denied_result(self) -> None:
        """Central execution engine returns DENIED when policy engine rejects."""
        req = TaskRequest(
            tool_name="pipeline_test.create_file",
            arguments={"filename": "bad.txt", "path": "C:\\Windows\\System32\\bad.dll"},
        )
        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            result = self.engine.execute(req)

        self.assertEqual(result.status, "DENIED")
        self.assertFalse(result.is_success)
        self.assertIn("Policy denied", result.message)

    # --- 6. Confirmation Required Result ---

    def test_confirmation_required_result(self) -> None:
        """Central execution engine returns NEED_CONFIRM with valid token for sensitive actions."""
        req = TaskRequest(
            tool_name="pipeline_test.sensitive_message",
            arguments={"message": "Meeting update"},
        )
        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            result = self.engine.execute(req)

        self.assertEqual(result.status, "NEED_CONFIRM")
        self.assertIn("token", result.data)
        token = result.data["token"]

        # Re-executing with the token succeeds
        req_confirmed = TaskRequest(
            tool_name="pipeline_test.sensitive_message",
            arguments={"message": "Meeting update"},
            confirmation_token=token,
        )
        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            res_after = self.engine.execute(req_confirmed)

        self.assertTrue(res_after.is_success)

    # --- 7. Timeout Handling ---

    def test_execution_timeout_returns_timeout_state(self) -> None:
        """Slow operation exceeding timeout returns TIMEOUT status."""
        req = TaskRequest(
            tool_name="pipeline_test.slow_operation",
            timeout_s=0.1,  # Short timeout
        )
        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            result = self.engine.execute(req)

        self.assertEqual(result.status, "TIMEOUT")
        self.assertFalse(result.is_success)
        self.assertIn("timeout", result.message.lower())

    # --- 8. Kill Switch Interruption ---

    def test_kill_switch_cancels_execution(self) -> None:
        """Active kill switch halts execution and returns CANCELLED."""
        self.kill_switch.activate(reason="Test active lockdown")
        req = TaskRequest(tool_name="pipeline_test.create_file", arguments={"filename": "a.txt"})

        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_kill_switch", return_value=self.kill_switch):
            result = self.engine.execute(req)

        self.assertEqual(result.status, "CANCELLED")
        self.assertFalse(result.is_success)
        self.assertIn("Emergency kill switch", result.message)

    # --- 9. Graceful Fallback & Bounded Retry ---

    def test_graceful_fallback_on_primary_failure(self) -> None:
        """When primary tool raises exception, registered fallback executes and marks fallback_used."""
        self.engine.register_fallback("pipeline_test.flaky_action", lambda: "Fallback execution succeeded")

        req = TaskRequest(tool_name="pipeline_test.flaky_action")
        with patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            result = self.engine.execute(req)

        self.assertTrue(result.is_success)
        self.assertTrue(result.data.get("fallback_used", False))
        self.assertIn("Fallback execution succeeded", result.message)

    # --- 10. Audit Lifecycle Recording ---

    def test_audit_lifecycle_events_recorded(self) -> None:
        """Lifecycle events (REQUESTED, VALIDATED, POLICY_CHECKED, TASK_EXECUTED, VERIFICATION_STARTED, TASK_COMPLETED) must be audited."""
        audit = get_audit_logger()
        recorded_types = []

        original_record = audit.record_event
        def _capture_event(event_type: str, *args: Any, **kwargs: Any) -> None:
            recorded_types.append(event_type)
            original_record(event_type, *args, **kwargs)

        req = TaskRequest(
            tool_name="pipeline_test.create_file",
            arguments={"filename": "audit.txt", "path": str(self.tmp_path / "audit.txt")},
        )
        with patch.object(audit, "record_event", side_effect=_capture_event), \
             patch("execution.engine.get_registry", return_value=self.registry), \
             patch("execution.engine.get_policy_engine", return_value=self.policy_engine):
            self.engine.execute(req)

        self.assertIn("TASK_REQUESTED", recorded_types)
        self.assertIn("TASK_VALIDATED", recorded_types)
        self.assertIn("POLICY_CHECKED", recorded_types)
        self.assertIn("TASK_EXECUTED", recorded_types)
        self.assertIn("VERIFICATION_STARTED", recorded_types)
        self.assertIn("VERIFICATION_COMPLETED", recorded_types)
        self.assertIn("TASK_COMPLETED", recorded_types)

    # --- 11. Legacy and OLIVER Routing Funnel Parity ---

    def test_legacy_and_oliver_route_through_central_engine(self) -> None:
        """Both router modes invoke tools through the central execution engine."""
        from ai.assistant import AshishAssistant
        from router.router import IntentRouter, RouteResult

        assistant = AshishAssistant()
        # Calling legacy execute_confirmed_command with shutdown
        with patch.object(self.engine, "execute", wraps=self.engine.execute) as mock_exec:
            with patch("execution.engine.get_execution_engine", return_value=self.engine):
                # Legacy route
                assistant.execute_confirmed_command("shutdown")
                self.assertTrue(mock_exec.called)
                last_call_req = mock_exec.call_args[0][0]
                self.assertEqual(last_call_req.tool_name, "windows.shutdown")
                self.assertTrue(last_call_req.user_confirmed)

        router = IntentRouter()
        route = RouteResult(matched=True, tool_name="pipeline_test.create_file", arguments={"filename": "r.txt"})
        with patch.object(self.engine, "execute", wraps=self.engine.execute) as mock_exec2:
            with patch("execution.engine.get_execution_engine", return_value=self.engine):
                router.execute_route(route)
                self.assertTrue(mock_exec2.called)
                req_oliver = mock_exec2.call_args[0][0]
                self.assertEqual(req_oliver.tool_name, "pipeline_test.create_file")


if __name__ == "__main__":
    unittest.main()
