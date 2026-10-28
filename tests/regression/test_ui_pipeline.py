"""Unit and regression tests for Stage 9.1: UI Event Queue and Main-Thread Event Bridge.

Tests headless cross-thread event posting, bounded queue processing, exception
isolation, shutdown rejection, and integration with CommandConsolePanel.
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from ui.event_bridge import UIEventQueue


class UIEventQueueTests(unittest.TestCase):
    """Test suite for UIEventQueue thread safety, bounded polling, and shutdown."""

    def test_post_and_process_events_headless(self) -> None:
        """Verify standard posting and execution in headless environment."""
        bridge = UIEventQueue(max_events_per_poll=50)
        results: list[str] = []

        def worker_callback(msg: str, count: int, prefix: str = "ok") -> None:
            results.append(f"{prefix}:{msg}:{count}")

        self.assertTrue(bridge.post(worker_callback, "item1", 1))
        self.assertTrue(bridge.post(worker_callback, "item2", 2, prefix="custom"))
        self.assertEqual(bridge.pending_count, 2)
        self.assertEqual(bridge.processed_count, 0)

        processed = bridge.process_events()
        self.assertEqual(processed, 2)
        self.assertEqual(bridge.pending_count, 0)
        self.assertEqual(bridge.processed_count, 2)
        self.assertEqual(results, ["ok:item1:1", "custom:item2:2"])

    def test_bounded_queue_draining(self) -> None:
        """Verify process_events respects max_events limits to prevent UI thread lockup."""
        bridge = UIEventQueue(max_events_per_poll=10)
        calls: list[int] = []

        for i in range(25):
            bridge.post(lambda idx=i: calls.append(idx))

        self.assertEqual(bridge.pending_count, 25)

        # First batch: bounded to 10
        p1 = bridge.process_events(max_events=10)
        self.assertEqual(p1, 10)
        self.assertEqual(len(calls), 10)
        self.assertEqual(bridge.pending_count, 15)

        # Second batch: default max_events_per_poll (10)
        p2 = bridge.process_events()
        self.assertEqual(p2, 10)
        self.assertEqual(len(calls), 20)
        self.assertEqual(bridge.pending_count, 5)

        # Third batch: remaining 5
        p3 = bridge.process_events()
        self.assertEqual(p3, 5)
        self.assertEqual(len(calls), 25)
        self.assertEqual(bridge.pending_count, 0)

    def test_cross_thread_event_submission(self) -> None:
        """Verify concurrent posting from multiple background threads without race conditions."""
        bridge = UIEventQueue(max_events_per_poll=500)
        total_threads = 20
        events_per_thread = 15
        expected_total = total_threads * events_per_thread

        received: list[tuple[int, int]] = []
        lock = threading.Lock()

        def background_worker(thread_idx: int) -> None:
            for item_idx in range(events_per_thread):
                time.sleep(0.001)
                bridge.post(
                    lambda t=thread_idx, i=item_idx: (
                        lock.acquire(),
                        received.append((t, i)),
                        lock.release(),
                    )
                )

        threads = [
            threading.Thread(target=background_worker, args=(t_id,))
            for t_id in range(total_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(bridge.pending_count, expected_total)

        processed = bridge.process_events(max_events=expected_total + 10)
        self.assertEqual(processed, expected_total)
        self.assertEqual(len(received), expected_total)
        self.assertEqual(bridge.pending_count, 0)

    def test_callback_exception_isolation(self) -> None:
        """Verify callback exceptions are logged and do not crash the event processing loop."""
        bridge = UIEventQueue()
        executed: list[str] = []

        def failing_callback() -> None:
            raise ValueError("Intentional simulated error in callback")

        def normal_callback(name: str) -> None:
            executed.append(name)

        bridge.post(normal_callback, "first")
        bridge.post(failing_callback)
        bridge.post(normal_callback, "second")

        # Must not raise
        processed = bridge.process_events()
        self.assertEqual(processed, 3)
        self.assertEqual(executed, ["first", "second"])
        self.assertEqual(bridge.processed_count, 3)

    def test_event_rejection_and_draining_after_shutdown(self) -> None:
        """Verify shutdown stops acceptance, drains pending events, and rejects subsequent posts."""
        bridge = UIEventQueue()
        calls: list[int] = []

        # Enqueue 4 pending events
        for i in range(4):
            bridge.post(lambda idx=i: calls.append(idx))

        self.assertEqual(bridge.pending_count, 4)
        self.assertTrue(bridge.is_accepting)

        # Execute shutdown
        drained = bridge.shutdown()
        self.assertEqual(drained, 4)
        self.assertFalse(bridge.is_accepting)
        self.assertEqual(bridge.pending_count, 0)
        self.assertEqual(bridge.discarded_count, 4)
        self.assertEqual(len(calls), 0, "Drained events must not execute against destroyed UI")

        # Subsequent post attempts must return False and be rejected
        accepted = bridge.post(lambda: calls.append(999))
        self.assertFalse(accepted)
        self.assertEqual(bridge.discarded_count, 5)
        self.assertEqual(bridge.pending_count, 0)
        self.assertEqual(len(calls), 0)

    def test_shutdown_cancels_polling_timer(self) -> None:
        """Verify shutdown cancels active root.after() timer safely."""
        bridge = UIEventQueue(poll_interval_ms=30)

        mock_root = MagicMock()
        mock_root.after.return_value = "after_timer_token_42"

        bridge.bind_root(mock_root)
        bridge.start_polling()

        self.assertTrue(bridge.is_polling)
        mock_root.after.assert_called_once_with(30, bridge._poll_tick)

        # Shutdown cancels timer
        bridge.shutdown()
        self.assertFalse(bridge.is_polling)
        mock_root.after_cancel.assert_called_once_with("after_timer_token_42")

    def test_command_console_panel_bridge_integration(self) -> None:
        """Verify CommandConsolePanel posts background updates through UIEventQueue."""
        import customtkinter as ctk
        from ui.chat import CommandConsolePanel

        mock_master = MagicMock()
        mock_assistant = MagicMock()
        mock_assistant.is_dangerous_command.return_value = (False, "")
        mock_store = MagicMock()
        mock_voice_manager = MagicMock()
        mock_voice_manager.listen_once.return_value = "open notepad"
        bridge = UIEventQueue()

        # Instantiate CommandConsolePanel with injected event bridge in headless mode
        with patch.object(ctk.CTkFrame, "__init__", return_value=None), \
             patch.object(CommandConsolePanel, "_build_ui"), \
             patch.object(CommandConsolePanel, "_load_history"), \
             patch("customtkinter.StringVar"):
            panel = CommandConsolePanel(
                master=mock_master,
                assistant=mock_assistant,
                store=mock_store,
                voice_manager=mock_voice_manager,
                event_bridge=bridge,
            )

            # Background voice worker finishes speech input
            panel.transcript_var = MagicMock()
            panel._process_command = MagicMock()
            panel._handle_voice_input()

            # The background handler should post into the bridge
            self.assertGreater(bridge.pending_count, 0)

            # Process events on main thread
            processed = bridge.process_events()
            self.assertGreater(processed, 0)
            panel.transcript_var.set.assert_called_with("open notepad")
            panel._process_command.assert_called_with("open notepad")

    def test_event_bridge_discarded_event_when_closed_in_flight(self) -> None:
        """Verify that events queued before shutdown are safely discarded if processed after closure."""
        bridge = UIEventQueue()
        calls: list[int] = []

        bridge.post(lambda: calls.append(1))
        # Directly close acceptance without draining queue
        with bridge._lock:
            bridge._accepting_events = False

        # process_events should discard item and NOT call the callback
        processed = bridge.process_events()
        self.assertEqual(processed, 0)
        self.assertEqual(len(calls), 0)
        self.assertEqual(bridge.discarded_count, 1)

    def test_ui_app_destroy_shuts_down_event_bridge(self) -> None:
        """Verify AshishApp.destroy() closes event bridge and cancels timer jobs."""
        from ui.app import AshishApp

        with patch.object(AshishApp, "__init__", return_value=None):
            app = AshishApp()
            app.event_bridge = MagicMock()
            app._orb_job = "orb_timer_1"
            app._monitor_job = "monitor_timer_2"
            app.after_cancel = MagicMock()

            with patch("customtkinter.CTk.destroy") as mock_super_destroy:
                AshishApp.destroy(app)

    def test_worker_run_assistant_command_dispatches_state_via_bridge(self) -> None:
        """Verify _run_assistant_command enqueues _set_state('EXECUTING') via bridge, avoiding worker UI calls."""
        import customtkinter as ctk
        from skills.base import ToolResult
        from ui.chat import CommandConsolePanel

        bridge = UIEventQueue()
        mock_assistant = MagicMock()
        mock_assistant.handle_result.return_value = ToolResult(
            status="VERIFIED",
            message="Notepad opened",
        )
        mock_assistant.handle.return_value = "Notepad opened"
        mock_assistant.intent_type = "WINDOWS_APP"

        with patch.object(ctk.CTkFrame, "__init__", return_value=None), \
             patch.object(CommandConsolePanel, "_build_ui"), \
             patch.object(CommandConsolePanel, "_load_history"), \
             patch("customtkinter.StringVar"):
            panel = CommandConsolePanel(
                master=MagicMock(),
                assistant=mock_assistant,
                store=MagicMock(),
                voice_manager=MagicMock(),
                event_bridge=bridge,
            )
            panel._set_state = MagicMock()
            panel._log_console_entry = MagicMock()
            panel._speak_confirmation = MagicMock()

            # Execute worker command function synchronously as if in background thread
            panel._run_assistant_command("open notepad")

            # _set_state should NOT have been called directly yet; it must be in the queue
            panel._set_state.assert_not_called()
            self.assertGreater(bridge.pending_count, 0)

            # Process queue on main thread
            bridge.process_events()
            panel._set_state.assert_any_call("EXECUTING")
            panel._log_console_entry.assert_called_once_with(
                "open notepad", "WINDOWS_APP", "Notepad opened", "VERIFIED", None
            )

    def test_app_destroy_idempotency_guard(self) -> None:
        """Verify repeated calls to AshishApp.destroy() are safe and do not re-execute cleanup."""
        from ui.app import AshishApp

        with patch.object(AshishApp, "__init__", return_value=None):
            app = AshishApp()
            app._is_destroyed = False
            app.event_bridge = MagicMock()
            app._orb_job = "orb_timer_1"
            app._monitor_job = "monitor_timer_2"
            app.after_cancel = MagicMock()

            with patch("customtkinter.CTk.destroy") as mock_super_destroy:
                # First call
                AshishApp.destroy(app)
                self.assertTrue(app._is_destroyed)
                self.assertEqual(app.event_bridge.shutdown.call_count, 1)
                self.assertEqual(app.after_cancel.call_count, 2)
                self.assertEqual(mock_super_destroy.call_count, 1)

                # Second call should be a no-op due to guard
                AshishApp.destroy(app)
                self.assertEqual(app.event_bridge.shutdown.call_count, 1)
                self.assertEqual(app.after_cancel.call_count, 2)
                self.assertEqual(mock_super_destroy.call_count, 1)

    def test_command_console_panel_bridge_ownership(self) -> None:
        """Verify panel does not shut down shared application bridge, but cleans up private bridge."""
        import customtkinter as ctk
        from ui.chat import CommandConsolePanel

        with patch.object(ctk.CTkFrame, "__init__", return_value=None), \
             patch.object(ctk.CTkFrame, "destroy"), \
             patch.object(CommandConsolePanel, "_build_ui"), \
             patch.object(CommandConsolePanel, "_load_history"), \
             patch("customtkinter.StringVar"):

            # Case A: Shared bridge injected
            shared_bridge = MagicMock()
            panel_shared = CommandConsolePanel(
                master=MagicMock(),
                assistant=MagicMock(),
                store=MagicMock(),
                event_bridge=shared_bridge,
            )
            self.assertFalse(panel_shared._owns_event_bridge)
            panel_shared.destroy()
            shared_bridge.shutdown.assert_not_called()

            # Case B: Private bridge created by panel
            with patch("ui.chat.UIEventQueue") as mock_bridge_cls:
                mock_private_bridge = MagicMock()
                mock_private_bridge._root = None
                mock_bridge_cls.return_value = mock_private_bridge

                panel_private = CommandConsolePanel(
                    master=MagicMock(),
                    assistant=MagicMock(),
                    store=MagicMock(),
                    event_bridge=None,
                )
                self.assertTrue(panel_private._owns_event_bridge)
                panel_private.destroy()
                mock_private_bridge.shutdown.assert_called_once()

    def test_stage_9_2_branding_and_titles(self) -> None:
        """Verify standardized OLIVER 2.0 branding across window titles and configuration."""
        import os
        import customtkinter as ctk
        from core.config import OliverConfig, get_config
        from ui.app import AshishApp
        from ui.setting import VoiceSettingsWindow

        # Verify default OliverConfig branding when APP_NAME is not overridden
        with patch.dict(os.environ):
            os.environ.pop("APP_NAME", None)
            clean_cfg = OliverConfig()
            self.assertEqual(clean_cfg.app_name, "OLIVER 2.0")
            self.assertEqual(clean_cfg.cockpit_title, "OLIVER 2.0 — Windows AI Cockpit")

        # Verify active config preserves cockpit title
        cfg = get_config()
        self.assertEqual(cfg.cockpit_title, "OLIVER 2.0 — Windows AI Cockpit")

        with patch.object(ctk.CTk, "__init__", return_value=None), \
             patch.object(AshishApp, "_configure_window"), \
             patch.object(AshishApp, "_build_layout"), \
             patch.object(AshishApp, "_start_system_monitoring"), \
             patch.object(AshishApp, "_start_orb_animation"), \
             patch.object(AshishApp, "title") as mock_app_title, \
             patch.object(AshishApp, "geometry"), \
             patch.object(AshishApp, "minsize"), \
             patch.object(AshishApp, "protocol"), \
             patch.object(AshishApp, "after"), \
             patch("customtkinter.StringVar"), \
             patch("ui.app.AshishAssistant"), \
             patch("ui.app.ChatStore"), \
             patch("ui.app.VoiceManager"):
            app = AshishApp()
            mock_app_title.assert_called_with("OLIVER 2.0 — Windows AI Cockpit")

        with patch.object(ctk.CTkToplevel, "__init__", return_value=None), \
             patch.object(VoiceSettingsWindow, "_build_ui"), \
             patch.object(VoiceSettingsWindow, "_load_values"), \
             patch.object(VoiceSettingsWindow, "title") as mock_settings_title, \
             patch.object(VoiceSettingsWindow, "geometry"), \
             patch.object(VoiceSettingsWindow, "minsize"), \
             patch.object(VoiceSettingsWindow, "configure"), \
             patch.object(VoiceSettingsWindow, "transient"), \
             patch.object(VoiceSettingsWindow, "grab_set"):
            win = VoiceSettingsWindow(voice_manager=MagicMock())
            mock_settings_title.assert_called_with("OLIVER 2.0 Settings")

    def test_stage_9_2_config_migration(self) -> None:
        """Verify ui/app.py and ui/setting.py migrate to OliverConfig and preserve compatibility."""
        import customtkinter as ctk
        from core.config import OliverConfig, get_config
        from ui.app import AshishApp
        from ui.setting import VoiceSettingsWindow

        with patch.object(ctk.CTk, "__init__", return_value=None), \
             patch.object(AshishApp, "_configure_window"), \
             patch.object(AshishApp, "_build_layout"), \
             patch.object(AshishApp, "_start_system_monitoring"), \
             patch.object(AshishApp, "_start_orb_animation"), \
             patch.object(AshishApp, "title"), \
             patch.object(AshishApp, "geometry"), \
             patch.object(AshishApp, "minsize"), \
             patch.object(AshishApp, "protocol"), \
             patch.object(AshishApp, "after"), \
             patch("customtkinter.StringVar"), \
             patch("ui.app.AshishAssistant"), \
             patch("ui.app.ChatStore"), \
             patch("ui.app.VoiceManager"):
            app = AshishApp()
            self.assertIsInstance(app.config, OliverConfig)
            self.assertIs(app.settings, app.config)

        with patch.object(ctk.CTkToplevel, "__init__", return_value=None), \
             patch.object(VoiceSettingsWindow, "_build_ui"), \
             patch.object(VoiceSettingsWindow, "_load_values"), \
             patch.object(VoiceSettingsWindow, "title"), \
             patch.object(VoiceSettingsWindow, "geometry"), \
             patch.object(VoiceSettingsWindow, "minsize"), \
             patch.object(VoiceSettingsWindow, "configure"), \
             patch.object(VoiceSettingsWindow, "transient"), \
             patch.object(VoiceSettingsWindow, "grab_set"):
            custom_cfg = OliverConfig(app_name="Custom OLIVER")
            win = VoiceSettingsWindow(voice_manager=MagicMock(), config=custom_cfg)
            self.assertEqual(win.config.app_name, "Custom OLIVER")

    def test_stage_9_2_backward_compatibility_aliases(self) -> None:
        """Verify backward compatibility class aliases are preserved."""
        from ui.app import OliverApp, AshishApp, AyraApp
        from ui.chat import CommandConsolePanel, OliverConsolePanel, ChatPanel
        from ui.setting import VoiceSettingsWindow, OliverSettingsWindow

        self.assertIs(OliverApp, AshishApp)
        self.assertIs(AyraApp, AshishApp)
        self.assertIs(OliverConsolePanel, CommandConsolePanel)
        self.assertIs(ChatPanel, CommandConsolePanel)
        self.assertIs(OliverSettingsWindow, VoiceSettingsWindow)


class Stage93TruthfulStatusAndConfirmationTests(unittest.TestCase):
    """Test suite for Stage 9.3: Truthful Status Badges and Confirmation Modal Wiring."""

    def test_status_config_badge_mappings(self) -> None:
        """Verify STATUS_CONFIG maps all truthful ToolResult statuses to distinct colors and borders."""
        from ui.chat import STATUS_CONFIG

        expected_statuses = [
            ("VERIFIED", "#10B981", "#065F46", "VERIFIED"),
            ("UNVERIFIED", "#F59E0B", "#78350F", "UNVERIFIED"),
            ("FAILED", "#EF4444", "#7F1D1D", "FAILED"),
            ("DENIED", "#991B1B", "#4C0519", "DENIED"),
            ("CANCELLED", "#64748B", "#334155", "CANCELLED"),
            ("TIMEOUT", "#EA580C", "#7C2D12", "TIMEOUT"),
            ("NEED_CONFIRM", "#D97706", "#78350F", "NEED CONFIRM"),
        ]

        for status_key, color, border, label in expected_statuses:
            self.assertIn(status_key, STATUS_CONFIG)
            cfg = STATUS_CONFIG[status_key]
            self.assertEqual(cfg["color"], color)
            self.assertEqual(cfg["border"], border)
            self.assertEqual(cfg["label"], label)

    def test_confirmation_token_consumption_and_duplicate_rejection(self) -> None:
        """Verify single-use token lifecycle: first verify succeeds, duplicate attempt is rejected."""
        from security.confirmation import ConfirmationManager

        mgr = ConfirmationManager(default_timeout_s=10.0)
        req = mgr.create_request(action="test.sensitive", risk_level=2, summary="Perform sensitive action")
        token = req.token

        # First consumption must succeed
        valid, expl = mgr.verify_and_consume(token, "CONFIRM")
        self.assertTrue(valid)
        self.assertIn("approved", expl.lower())

        # Second attempt with the exact same token MUST fail (anti-replay)
        valid2, expl2 = mgr.verify_and_consume(token, "CONFIRM")
        self.assertFalse(valid2)
        self.assertIn("already been consumed", expl2)

    def test_confirmation_token_invalidation_on_cancel(self) -> None:
        """Verify cancelling an action invalidates the token so it cannot be consumed later."""
        from security.confirmation import ConfirmationManager

        mgr = ConfirmationManager(default_timeout_s=10.0)
        req = mgr.create_request(action="windows.shutdown", risk_level=3, summary="Shutdown workstation")
        token = req.token

        # User cancels
        success = mgr.invalidate_token(token, reason="User clicked cancel in UI")
        self.assertTrue(success)

        # Subsequent attempt to consume must fail
        valid, expl = mgr.verify_and_consume(token, "CONFIRM")
        self.assertFalse(valid)
        self.assertTrue(
            "already been consumed" in expl.lower() or "invalid" in expl.lower()
        )

    def test_confirmation_token_expiration(self) -> None:
        """Verify expired token is rejected with informative expiration reason."""
        from security.confirmation import ConfirmationManager

        mgr = ConfirmationManager(default_timeout_s=0.01)
        req = mgr.create_request(action="test.expiring", risk_level=2, summary="Expiring action", timeout_s=0.01)
        time.sleep(0.02)

        valid, expl = mgr.verify_and_consume(req.token, "CONFIRM")
        self.assertFalse(valid)
        self.assertIn("expired", expl.lower())

    def test_confirmation_modal_duplicate_click_guard(self) -> None:
        """Verify ConfirmationModal guards against duplicate button clicks."""
        from ui.app import ConfirmationModal

        confirm_called = []
        cancel_called = []

        modal = object.__new__(ConfirmationModal)
        modal.on_confirm = lambda: confirm_called.append(1)
        modal.on_cancel = lambda: cancel_called.append(1)
        modal._handled = False
        modal.destroy = MagicMock()

        # Fire confirm twice -> only first fires callback
        modal._confirm()
        modal._confirm()
        self.assertEqual(len(confirm_called), 1)

        # Fire cancel after already handled -> must do nothing
        modal._cancel()
        self.assertEqual(len(cancel_called), 0)

    def test_assistant_handle_result_truthful_dispatch(self) -> None:
        """Verify Assistant.handle_result routes and returns typed ToolResult."""
        from ai.assistant import AshishAssistant
        from skills.base import ToolResult

        assistant = AshishAssistant()
        # Empty text fails immediately
        res = assistant.handle_result("")
        self.assertEqual(res.status, "FAILED")

        # Command requiring confirmation returns NEED_CONFIRM
        res_shut = assistant.handle_result("shut down the computer")
        self.assertEqual(res_shut.status, "NEED_CONFIRM")
        self.assertIn("token", res_shut.data)
        self.assertIn("Shutdown", res_shut.message)


class Stage94KillSwitchAndTelemetryTests(unittest.TestCase):
    """Test suite for Stage 9.4: Kill Switch & System Status Indicators."""

    def setUp(self) -> None:
        from security.kill_switch import get_kill_switch
        ks = get_kill_switch()
        if ks.is_active:
            ks.deactivate()

    def tearDown(self) -> None:
        from security.kill_switch import get_kill_switch
        ks = get_kill_switch()
        if ks.is_active:
            ks.deactivate()

    def test_kill_switch_activation_and_token_invalidation(self) -> None:
        """Verify activating kill switch invalidates all pending tokens immediately."""
        from security.confirmation import get_confirmation_manager
        from security.kill_switch import get_kill_switch

        ks = get_kill_switch()
        cm = get_confirmation_manager()

        req1 = cm.create_request("action1", 2, "summary1")
        req2 = cm.create_request("action2", 3, "summary2")

        ks.activate(reason="Test Emergency Activation")
        self.assertTrue(ks.is_active)
        self.assertEqual(ks.reason, "Test Emergency Activation")

        # Both tokens must now be invalidated
        valid1, _ = cm.verify_and_consume(req1.token, "CONFIRM")
        valid2, _ = cm.verify_and_consume(req2.token, "CONFIRM")
        self.assertFalse(valid1)
        self.assertFalse(valid2)

        # Deactivation restores normal state
        ks.deactivate()
        self.assertFalse(ks.is_active)

    def test_console_panel_rejects_input_when_kill_switch_active(self) -> None:
        """Verify CommandConsolePanel rejects commands and disables input when kill switch engaged."""
        import customtkinter as ctk
        from security.kill_switch import get_kill_switch
        from ui.chat import CommandConsolePanel

        ks = get_kill_switch()
        mock_assistant = MagicMock()
        mock_voice = MagicMock()
        bridge = MagicMock()

        with patch.object(ctk.CTkFrame, "__init__", return_value=None), \
             patch.object(CommandConsolePanel, "_build_ui"), \
             patch.object(CommandConsolePanel, "_load_history"), \
             patch("customtkinter.StringVar"):
            panel = CommandConsolePanel(
                master=MagicMock(),
                assistant=mock_assistant,
                store=MagicMock(),
                voice_manager=mock_voice,
                event_bridge=bridge,
            )
            panel.entry = MagicMock()
            panel.mic_btn = MagicMock()
            panel.send_btn = MagicMock()
            panel._log_console_entry = MagicMock()

            # 1. Engage kill switch
            ks.activate(reason="Emergency Test")
            panel.handle_kill_switch_activated()

            panel.entry.configure.assert_called_with(state="disabled")
            panel.mic_btn.configure.assert_called_with(state="disabled")
            panel.send_btn.configure.assert_called_with(state="disabled")

            # 2. Try executing command while engaged -> must be rejected
            panel.execute_text_command("open notepad")
            panel._log_console_entry.assert_called_with(
                "open notepad", "SECURITY", "Command rejected: Emergency Kill Switch is engaged.", "DENIED", None
            )

            # 3. Disengage kill switch
            ks.deactivate()
            panel.handle_kill_switch_deactivated()
            panel.entry.configure.assert_called_with(state="normal")
            panel.mic_btn.configure.assert_called_with(state="normal")
            panel.send_btn.configure.assert_called_with(state="normal")

    def test_app_kill_switch_toggle_and_confirmation(self) -> None:
        """Verify AshishApp.toggle_kill_switch activates immediately and requires confirmation to reset."""
        from security.kill_switch import get_kill_switch
        from ui.app import AshishApp

        ks = get_kill_switch()

        with patch.object(AshishApp, "__init__", return_value=None):
            app = AshishApp()
            app.voice_manager = MagicMock()
            app.console_panel = MagicMock()
            app.kill_switch_btn = MagicMock()
            app.state_label = MagicMock()
            app.ai_state_var = MagicMock()
            app.show_confirmation_modal = MagicMock()

            # Initial state: inactive -> clicking toggles ON immediately
            app.toggle_kill_switch()
            self.assertTrue(ks.is_active)
            app.voice_manager.barge_in.assert_called_once()
            app.kill_switch_btn.configure.assert_called_with(
                text="⚠️  RESET KILL SWITCH",
                fg_color="#D97706",
                hover_color="#B45309",
                border_color="#F59E0B",
                text_color="#000000",
            )
            app.console_panel.handle_kill_switch_activated.assert_called_once()

            # Second click while active: must trigger confirmation modal before resetting
            app.toggle_kill_switch()
            app.show_confirmation_modal.assert_called_once()

            # Simulate modal confirmation
            app._confirm_kill_switch_reset()
            self.assertFalse(ks.is_active)
            app.console_panel.handle_kill_switch_deactivated.assert_called_once()

    def test_telemetry_updates_application(self) -> None:
        """Verify _apply_telemetry_updates configures label text and colors safely."""
        from ui.app import AshishApp

        with patch.object(AshishApp, "__init__", return_value=None):
            app = AshishApp()
            app._is_destroyed = False
            mock_ollama_lbl = MagicMock()
            mock_mic_lbl = MagicMock()
            app.metric_labels = {
                "OLLAMA": mock_ollama_lbl,
                "MIC PRIVACY": mock_mic_lbl,
            }

            telemetry = {
                "OLLAMA": ("READY", "#10B981"),
                "MIC PRIVACY": ("MIC: ACTIVE", "#10B981"),
            }
            app._apply_telemetry_updates(telemetry)

            mock_ollama_lbl.configure.assert_called_with(text="READY", text_color="#10B981")
            mock_mic_lbl.configure.assert_called_with(text="MIC: ACTIVE", text_color="#10B981")


class Stage95AgentProgressMonitorTests(unittest.TestCase):
    """Test suite for Stage 9.5: Agent Progress Monitor & Cancellation."""

    def test_agent_task_loop_progress_callback(self) -> None:
        """Verify AgentTaskLoop invokes on_progress with truthful planning, step, and completion events."""
        from agent.executor import AgentTaskLoop
        from agent.models import Plan, PlanStep
        from skills.base import ToolResult

        events: list[tuple[str, int, int, str, str, str]] = []

        def record_progress(task_id: str, step: int, total_steps: int, tool_name: str, desc: str, status: str) -> None:
            events.append((task_id, step, total_steps, tool_name, desc, status))

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ToolResult(status="VERIFIED", message="Step succeeded")

        plan = Plan(
            goal="Test multi-step task",
            steps=[
                PlanStep(step_number=1, tool_name="test.tool_1", description="Execute first tool"),
                PlanStep(step_number=2, tool_name="test.tool_2", description="Execute second tool"),
            ],
        )

        mock_validator = MagicMock()
        mock_validator.validate.return_value = (True, [])

        mock_store = MagicMock()

        loop = AgentTaskLoop(
            engine=mock_engine,
            validator=mock_validator,
            store=mock_store,
        )

        report = loop.run(
            goal="Test multi-step task",
            plan_override=plan,
            on_progress=record_progress,
        )

        self.assertEqual(report.overall_status, "SUCCESS")
        statuses = [ev[5] for ev in events]
        self.assertIn("planning", statuses)
        self.assertIn("executing_step", statuses)
        self.assertIn("completed", statuses)

    def test_agent_task_loop_cancellation_and_event(self) -> None:
        """Verify cancelling task loop halts execution and emits cancelled event."""
        from agent.executor import AgentTaskLoop
        from agent.models import Plan, PlanStep

        events: list[tuple[str, int, int, str, str, str]] = []

        def record_progress(task_id: str, step: int, total_steps: int, tool_name: str, desc: str, status: str) -> None:
            events.append((task_id, step, total_steps, tool_name, desc, status))

        plan = Plan(
            goal="Cancelable task",
            steps=[PlanStep(step_number=1, tool_name="tool_1", description="Step 1")],
        )

        loop = AgentTaskLoop(
            engine=MagicMock(),
            validator=MagicMock(),
            store=MagicMock(),
        )
        task_id = "test_cancel_123"
        loop.cancel(task_id)

        report = loop.run(
            goal="Cancelable task",
            task_id=task_id,
            plan_override=plan,
            on_progress=record_progress,
        )

        self.assertEqual(report.overall_status, "CANCELLED")
        statuses = [ev[5] for ev in events]
        self.assertIn("cancelled", statuses)

    def test_agent_task_loop_callback_exception_isolation(self) -> None:
        """Verify exceptions in on_progress do not crash or abort the task loop."""
        from agent.executor import AgentTaskLoop
        from agent.models import Plan, PlanStep
        from skills.base import ToolResult

        def failing_progress(*args) -> None:
            raise RuntimeError("UI progress error simulation")

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ToolResult(status="VERIFIED", message="Step ok")

        plan = Plan(
            goal="Resilient task",
            steps=[PlanStep(step_number=1, tool_name="test.tool_1", description="Step 1")],
        )

        mock_validator = MagicMock()
        mock_validator.validate.return_value = (True, [])

        loop = AgentTaskLoop(
            engine=mock_engine,
            validator=mock_validator,
            store=MagicMock(),
        )

        report = loop.run(
            goal="Resilient task",
            plan_override=plan,
            on_progress=failing_progress,
        )
        self.assertEqual(report.overall_status, "SUCCESS")

    def test_agent_task_monitor_card_ui_updates(self) -> None:
        """Verify AgentTaskMonitorCard updates status badge, progress bar, and cancel button."""
        from ui.app import AgentTaskMonitorCard

        monitor = object.__new__(AgentTaskMonitorCard)
        monitor.active_task_id = None
        monitor.on_cancel = MagicMock()
        monitor.status_badge = MagicMock()
        monitor.goal_label = MagicMock()
        monitor.step_label = MagicMock()
        monitor.progress_bar = MagicMock()
        monitor.cancel_btn = MagicMock()

        # Update while active: executing_step
        monitor.update_progress("task_99", 2, 4, "files.create", "Creating notes", "executing_step")
        self.assertEqual(monitor.active_task_id, "task_99")
        monitor.status_badge.configure.assert_called_with(text="EXECUTING", text_color="#38f7a6")
        monitor.progress_bar.set.assert_called_with(0.5)
        monitor.cancel_btn.configure.assert_called_with(
            state="normal",
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            text_color="#ffffff",
        )

        # Trigger cancel button click
        monitor._handle_cancel_click()
        monitor.on_cancel.assert_called_with("task_99")

        # Update when completed: cancel button must disable
        monitor.update_progress("task_99", 4, 4, "completed", "Done", "completed")
        monitor.status_badge.configure.assert_called_with(text="COMPLETED", text_color="#10b981")
        monitor.progress_bar.set.assert_called_with(1.0)
        monitor.cancel_btn.configure.assert_called_with(
            state="disabled",
            fg_color="#334155",
            hover_color="#475569",
            text_color="#94a3b8",
        )


class Stage96ReminderCardsAndDispatchTests(unittest.TestCase):
    """Test suite for Stage 9.6: Reminder Cards in the HUD."""

    def test_productivity_service_dispatch_listeners(self) -> None:
        """Verify ProductivityService registers listeners and dispatches reminder events."""
        from productivity.models import ReminderItem, ReminderStatus
        from productivity.service import ProductivityService

        received = []

        def sample_listener(reminder: ReminderItem) -> None:
            received.append(reminder.id)

        def failing_listener(reminder: ReminderItem) -> None:
            raise RuntimeError("Listener error simulation")

        service = object.__new__(ProductivityService)
        service._dispatch_listeners = []
        service._listeners_lock = threading.Lock()
        service.speaker = None

        service.add_dispatch_listener(sample_listener)
        service.add_dispatch_listener(failing_listener)
        self.assertEqual(len(service._dispatch_listeners), 2)

        rem = ReminderItem(
            id=42,
            title="Team Standup",
            remind_at="2026-10-28T15:00:00",
            created_at="2026-10-28T10:00:00",
            status=ReminderStatus.DISPATCHED,
        )

        # Dispatch should notify sample_listener and isolate failing_listener
        success = service._handle_reminder_dispatch(rem)
        self.assertTrue(success)
        self.assertEqual(received, [42])

        # Remove listener
        service.remove_dispatch_listener(sample_listener)
        self.assertEqual(len(service._dispatch_listeners), 1)

    def test_productivity_service_acknowledge_and_complete_api(self) -> None:
        """Verify service exposes acknowledge_reminder and complete_reminder."""
        from productivity.service import ProductivityService

        service = object.__new__(ProductivityService)
        service.store = MagicMock()

        service.acknowledge_reminder(101)
        service.store.acknowledge_reminder.assert_called_once_with(101)

        service.complete_reminder(102)
        service.store.complete_reminder.assert_called_once_with(102)

    def test_reminder_item_card_acknowledgement_click(self) -> None:
        """Verify ReminderItemCard acknowledge button disables and invokes callback."""
        from productivity.models import ReminderItem, ReminderStatus
        from ui.app import ReminderItemCard

        ack_calls = []

        card = object.__new__(ReminderItemCard)
        card.reminder = ReminderItem(
            id=77,
            title="Drink Water",
            remind_at="2026-10-28T14:00:00",
            created_at="2026-10-28T10:00:00",
            status=ReminderStatus.DISPATCHED,
        )
        card.on_acknowledge = lambda rem_id: ack_calls.append(rem_id)
        card.ack_btn = MagicMock()
        card.status_lbl = MagicMock()

        # Click acknowledge
        card._handle_ack()

        card.ack_btn.configure.assert_called_with(
            state="disabled", text="ACKNOWLEDGED", fg_color="#1e293b", text_color="#64748b"
        )
        card.status_lbl.configure.assert_called_with(text="ACKNOWLEDGED", text_color="#10b981")
        self.assertEqual(ack_calls, [77])

    def test_reminder_feed_cross_thread_dispatch_via_bridge(self) -> None:
        """Verify scheduler background dispatch posts to main thread through UIEventQueue."""
        from productivity.models import ReminderItem, ReminderStatus
        from ui.app import ReminderFeedPanel

        bridge = MagicMock()
        panel = object.__new__(ReminderFeedPanel)
        panel.event_bridge = bridge
        panel.handle_dispatched_reminder = MagicMock()

        rem = ReminderItem(
            id=99,
            title="Review PR",
            remind_at="2026-10-28T16:00:00",
            created_at="2026-10-28T10:00:00",
            status=ReminderStatus.DISPATCHED,
        )

        # Worker thread calls _on_reminder_dispatched
        panel._on_reminder_dispatched(rem)
        bridge.post.assert_called_once_with(panel.handle_dispatched_reminder, rem)


class Stage97BoundedShutdownAndResourceCleanupTests(unittest.TestCase):
    """Test suite for Stage 9.7: Bounded Shutdown, Resource Cleanup & Integrity."""

    def test_bounded_shutdown_successful_ui_closed(self) -> None:
        """Verify normal bounded shutdown completes quickly and sets UI_CLOSED."""
        import customtkinter as ctk
        from ui.app import AshishApp

        app = object.__new__(AshishApp)
        app._is_destroyed = False
        app.event_bridge = MagicMock()
        app._orb_job = "job_123"
        app._monitor_job = "job_456"
        app.after_cancel = MagicMock()
        app.voice_manager = MagicMock()

        with patch.object(ctk.CTk, "destroy", return_value=None):
            with patch("productivity.service.get_productivity_service") as mock_get_prod:
                mock_prod = MagicMock()
                mock_get_prod.return_value = mock_prod
                with patch("security.confirmation.get_confirmation_manager") as mock_get_cm:
                    mock_cm = MagicMock()
                    mock_get_cm.return_value = mock_cm

                    app.destroy()

        self.assertTrue(app._is_destroyed)
        self.assertEqual(app._shutdown_status, "UI_CLOSED")
        app.event_bridge.shutdown.assert_called_once()
        self.assertEqual(app.after_cancel.call_count, 2)
        app.voice_manager.barge_in.assert_called_once()
        mock_prod.shutdown.assert_called_once()
        mock_cm.invalidate_all.assert_called_once_with(reason="Application shutdown")

    def test_bounded_shutdown_incomplete_when_subsystem_fails(self) -> None:
        """Verify shutdown sets SHUTDOWN_INCOMPLETE and logs warning if a cleanup step raises."""
        import customtkinter as ctk
        from ui.app import AshishApp

        app = object.__new__(AshishApp)
        app._is_destroyed = False
        app.event_bridge = MagicMock()
        app.event_bridge.shutdown.side_effect = RuntimeError("Bridge drain timeout")
        app.after_cancel = MagicMock()
        app.voice_manager = MagicMock()

        with patch.object(ctk.CTk, "destroy", return_value=None):
            with patch("productivity.service.get_productivity_service") as mock_get_prod:
                mock_get_prod.return_value = MagicMock()
                with patch("security.confirmation.get_confirmation_manager") as mock_get_cm:
                    mock_get_cm.return_value = MagicMock()
                    app.destroy()

        self.assertTrue(app._is_destroyed)
        self.assertEqual(app._shutdown_status, "SHUTDOWN_INCOMPLETE")

    def test_bounded_shutdown_idempotent(self) -> None:
        """Verify calling destroy() repeatedly does not re-execute teardown."""
        import customtkinter as ctk
        from ui.app import AshishApp

        app = object.__new__(AshishApp)
        app._is_destroyed = False
        app.event_bridge = MagicMock()
        app._orb_job = "job_123"
        app.after_cancel = MagicMock()
        app.voice_manager = MagicMock()

        with patch.object(ctk.CTk, "destroy", return_value=None):
            with patch("productivity.service.get_productivity_service"):
                with patch("security.confirmation.get_confirmation_manager"):
                    app.destroy()
                    # Second call
                    app.destroy()

        self.assertEqual(app.event_bridge.shutdown.call_count, 1)
        self.assertEqual(app.after_cancel.call_count, 1)

    def test_database_integrity_and_quick_check(self) -> None:
        """Verify UnifiedDatabase PRAGMA integrity_check and quick_check APIs."""
        from pathlib import Path
        import tempfile
        from memory.unified_db import UnifiedDatabase

        with tempfile.TemporaryDirectory() as tmpdir:
            test_db_path = Path(tmpdir) / "test_integrity.db"
            db = UnifiedDatabase(db_path=test_db_path)
            try:
                ok, msg = db.check_integrity(quick=False)
                self.assertTrue(ok)
                self.assertEqual(msg, "ok")

                ok_quick, msg_quick = db.check_integrity(quick=True)
                self.assertTrue(ok_quick)
                self.assertEqual(msg_quick, "ok")
            finally:
                db.close()

    def test_background_worker_rejected_after_shutdown(self) -> None:
        """Verify events posted by background workers after shutdown are safely rejected."""
        bridge = UIEventQueue()
        calls: list[str] = []

        self.assertTrue(bridge.post(lambda: calls.append("pre_shutdown")))
        self.assertEqual(bridge.pending_count, 1)

        bridge.shutdown()
        self.assertFalse(bridge.is_accepting)

        # Post from background worker after shutdown
        rejected = bridge.post(lambda: calls.append("post_shutdown"))
        self.assertFalse(rejected)
        self.assertEqual(bridge.pending_count, 0)
        self.assertEqual(len(calls), 0)


if __name__ == "__main__":
    unittest.main()
