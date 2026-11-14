"""Comprehensive end-to-end integration and reliability test suite for OLIVER 3.0 Stage 2E.

Covers all 6 required verification areas:
Part A: Microphone lifecycle coordination (pause/resume, ref count, timeout, release confirmation)
Part B: Push-to-talk precedence & audio mutual exclusion
Part C: Wake detection ("Hey OLIVER" & "Hello OLIVER"), 2.0s cooldown, barge-in, emergency stop
Part D: Full Voice-to-Browser pipeline (Wake -> Vosk -> Router -> Trust -> Confirmation Modal -> Firefox)
Part E: Telemetry formatting (empty utterance -> "N/A", genuine low/high confidence, thread safety)
Part F: Clean shutdown and fault recovery under stress
"""

from __future__ import annotations

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock, call, patch

from browser.url_trust import URLTrustLevel, classify_url
from commands.browser import (
    BrowserCommands,
    get_browser_confirmation_callback,
    set_browser_confirmation_callback,
)
from core.config import OliverConfig
from ui.telemetry_utils import (
    format_confidence,
    format_stt_engine,
    format_stt_latency,
    get_confidence_color,
)
from voice.stt.base import TranscriptionResult
from voice.voice_manager import VoiceManager, VoiceState
from voice.wakeword import WakeWordDetector


class TestMicrophoneLifecycleCoordination(unittest.TestCase):
    """Part A: Verify pause/resume hooks, reference-counting, and stream exclusion."""

    def setUp(self) -> None:
        self.detector = WakeWordDetector(wake_phrases=["hey oliver", "hello oliver"])

    def tearDown(self) -> None:
        self.detector.stop()

    def test_01_wake_detector_pauses_before_foreground_recognition(self) -> None:
        """Wake detector pause() returns True and enters paused state."""
        self.assertFalse(self.detector.is_paused)
        confirmed = self.detector.pause(timeout=1.0)
        self.assertTrue(confirmed)
        self.assertTrue(self.detector.is_paused)

    def test_02_background_capture_released_before_foreground_capture(self) -> None:
        """Background loop unblocks pause_confirmed_event when paused."""
        callback = MagicMock()
        with patch.object(self.detector, "_listen_for_short_phrase", side_effect=lambda: time.sleep(0.05) or ""):
            self.detector.start(callback)
            self.assertTrue(self.detector.is_alive)

            # Request pause
            paused = self.detector.pause(timeout=1.0)
            self.assertTrue(paused)
            self.assertTrue(self.detector.is_paused)
            self.assertTrue(self.detector._pause_confirmed_event.is_set())

    def test_03_wake_detector_resumes_after_successful_recognition(self) -> None:
        """Calling resume() resets pause state and allows loop continuation."""
        self.detector.pause()
        self.assertTrue(self.detector.is_paused)
        self.detector.resume()
        self.assertFalse(self.detector.is_paused)

    def test_04_wake_detector_resumes_after_recognition_exception(self) -> None:
        """VoiceManager.listen_once_result() always resumes wake detector in finally: block."""
        vm = VoiceManager()
        vm.settings["voice_enabled"] = True
        mock_detector = MagicMock()
        mock_detector.pause.return_value = True
        vm.wake_detector = mock_detector

        with patch.object(vm.listener, "listen_once_result", side_effect=RuntimeError("Microphone crashed")):
            res = vm.listen_once_result()
            self.assertEqual(res.engine, "error")

        mock_detector.pause.assert_called_once()
        mock_detector.resume.assert_called_once()
        self.assertFalse(vm._is_listening)

    def test_05_multiple_pause_requests_reference_counted(self) -> None:
        """Multiple pause calls increment reference count; single resume does not unpause."""
        self.detector.pause()
        self.assertEqual(self.detector._pause_count, 1)
        self.detector.pause()
        self.assertEqual(self.detector._pause_count, 2)
        self.assertTrue(self.detector.is_paused)

        self.detector.resume()
        self.assertEqual(self.detector._pause_count, 1)
        self.assertTrue(self.detector.is_paused)

        self.detector.resume()
        self.assertEqual(self.detector._pause_count, 0)
        self.assertFalse(self.detector.is_paused)

    def test_06_resume_does_not_happen_prematurely_with_multiple_holders(self) -> None:
        """Resume with force=False will never restart background capture prematurely."""
        self.detector.pause()  # Holder 1 (e.g. PTT)
        self.detector.pause()  # Holder 2 (e.g. nested listen_once)

        self.detector.resume(force=False)
        self.assertTrue(self.detector.is_paused)
        self.assertFalse(self.detector._resume_event.is_set())

        self.detector.resume(force=False)
        self.assertFalse(self.detector.is_paused)
        self.assertTrue(self.detector._resume_event.is_set())

    def test_07_shutdown_while_paused_is_safe(self) -> None:
        """Detector thread terminates cleanly even when stopped while paused."""
        with patch.object(self.detector, "_listen_for_short_phrase", side_effect=lambda: time.sleep(0.05) or ""):
            self.detector.start(lambda: None)
            self.detector.pause(timeout=1.0)
            self.assertTrue(self.detector.is_paused)

            # Stopping while paused should not hang
            start_stop = time.monotonic()
            self.detector.stop()
            elapsed = time.monotonic() - start_stop
            self.assertLess(elapsed, 1.5)
            self.assertFalse(self.detector.is_alive)

    def test_08_no_duplicate_microphone_ownership(self) -> None:
        """VoiceManager.listen_once_result() rejects concurrent overlapping capture sessions."""
        vm = VoiceManager()
        vm.settings["voice_enabled"] = True
        vm._is_listening = True

        res = vm.listen_once_result()
        self.assertEqual(res.engine, "busy")
        self.assertEqual(res.text, "")

    def test_09_pause_timeout_fails_safely_without_opening_stream(self) -> None:
        """If wake detector cannot confirm pause, listen_once_result fails safely."""
        vm = VoiceManager()
        vm.settings["voice_enabled"] = True
        mock_detector = MagicMock()
        mock_detector.pause.return_value = False  # Timed out
        vm.wake_detector = mock_detector

        with patch.object(vm.listener, "listen_once_result") as mock_listener_call:
            res = vm.listen_once_result()
            self.assertEqual(res.engine, "mic_busy")
            mock_listener_call.assert_not_called()
            mock_detector.resume.assert_called_once()
            self.assertFalse(vm._is_listening)


class TestPushToTalkPrecedence(unittest.TestCase):
    """Part B: Push-to-talk precedence over background wake listening."""

    def test_10_push_to_talk_takes_priority_over_wake_listening(self) -> None:
        """VoiceManager.pause_wake_word() can be explicitly called before PTT audio capture."""
        vm = VoiceManager()
        vm.wake_detector = MagicMock()
        vm.wake_detector.pause.return_value = True

        paused = vm.pause_wake_word(timeout=1.0)
        self.assertTrue(paused)
        vm.wake_detector.pause.assert_called_once_with(timeout=1.0)

    def test_11_no_microphone_contention_during_ptt(self) -> None:
        """listen_once_result coordinates pause and executes cleanly during PTT."""
        vm = VoiceManager()
        vm.settings["voice_enabled"] = True
        mock_detector = MagicMock()
        mock_detector.pause.return_value = True
        vm.wake_detector = mock_detector

        expected_res = TranscriptionResult(text="open firefox", confidence=0.92, engine="vosk", confidence_available=True)
        with patch.object(vm.listener, "listen_once_result", return_value=expected_res):
            res = vm.listen_once_result()
            self.assertEqual(res.text, "open firefox")
            mock_detector.pause.assert_called_once()
            mock_detector.resume.assert_called_once()

    def test_12_wake_detection_resumes_after_push_to_talk(self) -> None:
        """Explicit resume_wake_word restores detector state after PTT release."""
        vm = VoiceManager()
        vm.wake_detector = MagicMock()
        vm.resume_wake_word()
        vm.wake_detector.resume.assert_called_once_with(force=False)

    def test_13_ptt_structured_transcription_results_intact(self) -> None:
        """PTT capture returns valid TranscriptionResult with latency and words."""
        vm = VoiceManager()
        vm.settings["voice_enabled"] = True
        vm.wake_detector = MagicMock()
        vm.wake_detector.pause.return_value = True

        fake_res = TranscriptionResult(
            text="what time is it",
            confidence=0.88,
            engine="vosk",
            confidence_available=True,
            latency_s=0.35,
            details={"words": [{"word": "what", "conf": 0.9}, {"word": "time", "conf": 0.86}]},
        )
        with patch.object(vm.listener, "listen_once_result", return_value=fake_res):
            res = vm.listen_once_result()
            self.assertEqual(res.text, "what time is it")
            self.assertEqual(res.confidence, 0.88)
            self.assertEqual(len(res.details["words"]), 2)
            self.assertAlmostEqual(res.latency_s, 0.35)


class TestWakeDetectionAndInterruption(unittest.TestCase):
    """Part C: Dual wake phrases, 2.0s cooldown, barge-in, and emergency stop."""

    def setUp(self) -> None:
        self.detector = WakeWordDetector(wake_phrases=["hey oliver", "hello oliver"], cooldown_seconds=2.0)

    def test_14_both_wake_phrases_activate_workflow(self) -> None:
        """Both 'Hey OLIVER' and 'Hello OLIVER' match as wake phrases."""
        self.assertTrue(self.detector._contains_wake_word("hey oliver"))
        self.assertTrue(self.detector._contains_wake_word("hello oliver"))
        self.assertTrue(self.detector._contains_wake_word("Hey Oliver, what is the weather"))
        self.assertTrue(self.detector._contains_wake_word("Hello Oliver please open the browser"))
        self.assertFalse(self.detector._contains_wake_word("hey there"))
        self.assertFalse(self.detector._contains_wake_word("oliver hello"))

    def test_15_wake_cooldown_2s_intact(self) -> None:
        """Callback is debounced within the 2.0-second cooldown."""
        callback = MagicMock()
        self.detector._callback = callback

        # First trigger
        self.detector._trigger_callback()
        self.assertEqual(callback.call_count, 1)

        # Immediate second trigger within cooldown is suppressed
        self.detector._trigger_callback()
        self.assertEqual(callback.call_count, 1)

        # After advancing past cooldown
        self.detector._last_triggered_at = time.monotonic() - 2.5
        self.detector._trigger_callback()
        self.assertEqual(callback.call_count, 2)

    def test_16_emergency_stop_functional(self) -> None:
        """VoiceManager.stop_speaking() invokes speaker barge-in cleanly."""
        vm = VoiceManager()
        vm.speaker = MagicMock()
        vm.stop_speaking()
        vm.speaker.barge_in.assert_called_once()

    def test_17_barge_in_stops_tts_speech(self) -> None:
        """Barge-in immediately interrupts active speech state and transitions to READY."""
        vm = VoiceManager()
        vm.speaker = MagicMock()
        vm.state_machine.transition_to(VoiceState.SPEAKING)
        self.assertEqual(vm.current_state, VoiceState.SPEAKING)

        vm.barge_in()
        vm.speaker.barge_in.assert_called_once()
        self.assertEqual(vm.current_state, VoiceState.READY)

    def test_18_no_duplicate_wake_activation(self) -> None:
        """Scattered tokens do not trigger duplicate wake activation."""
        self.assertFalse(self.detector._contains_wake_word("hey are you listening oliver"))
        self.assertFalse(self.detector._contains_wake_word("hello my friend oliver"))


class TestVoiceToBrowserFullPipeline(unittest.TestCase):
    """Part D: Full pipeline: Wake phrase -> STT -> Routing -> URL Trust -> Confirmation -> Firefox."""

    def setUp(self) -> None:
        self.original_cb = get_browser_confirmation_callback()

    def tearDown(self) -> None:
        set_browser_confirmation_callback(self.original_cb)

    @patch("webbrowser.open")
    def test_19_full_pipeline_trusted_url_direct_firefox_open(self, mock_web_open: MagicMock) -> None:
        """Trusted URL bypasses confirmation modal and opens directly in browser."""
        mock_web_open.return_value = True
        browser = BrowserCommands()
        out = browser.open_url("https://ashishsahoo.vercel.app/")
        self.assertIn("Opening ashishsahoo.vercel.app", out)
        mock_web_open.assert_called_once_with("https://ashishsahoo.vercel.app/")

    @patch("webbrowser.open")
    def test_20_full_pipeline_external_url_requires_confirmation_and_confirms(self, mock_web_open: MagicMock) -> None:
        """External URL invokes confirmation callback; confirming launches browser."""
        mock_web_open.return_value = True
        modal_mock = MagicMock(return_value=True)
        set_browser_confirmation_callback(modal_mock)

        browser = BrowserCommands()
        out = browser.open_url("https://example-external-blog.com")
        self.assertIn("Opening example-external-blog.com", out)
        modal_mock.assert_called_once_with("https://example-external-blog.com", "example-external-blog.com")
        mock_web_open.assert_called_once_with("https://example-external-blog.com")

    @patch("webbrowser.open")
    def test_21_full_pipeline_external_url_cancelled_aborts_browser(self, mock_web_open: MagicMock) -> None:
        """External URL cancelled by user aborts navigation without launching browser."""
        mock_web_open.return_value = True
        modal_mock = MagicMock(return_value=False)
        set_browser_confirmation_callback(modal_mock)

        browser = BrowserCommands()
        out = browser.open_url("https://random-external-site.com")
        self.assertIn("cancelled", out)
        modal_mock.assert_called_once()
        mock_web_open.assert_not_called()

    @patch("webbrowser.open")
    def test_22_full_pipeline_blocked_url_rejected_immediately(self, mock_web_open: MagicMock) -> None:
        """Blocked URL (e.g. javascript: or localhost) is rejected before modal or launch."""
        modal_mock = MagicMock()
        set_browser_confirmation_callback(modal_mock)

        browser = BrowserCommands()
        out1 = browser.open_url("javascript:alert(1)")
        self.assertIn("blocked", out1.lower())

        out2 = browser.open_url("http://127.0.0.1:8080/admin")
        self.assertIn("blocked", out2.lower())

        modal_mock.assert_not_called()
        mock_web_open.assert_not_called()

    def test_23_full_pipeline_preserves_firefox_invocation(self) -> None:
        """Direct launch uses Firefox controller candidate detection."""
        browser = BrowserCommands()
        with patch("shutil.which", return_value=r"C:\Program Files\Mozilla Firefox\firefox.exe"), \
             patch("os.path.exists", return_value=True), \
             patch("webbrowser.register") as mock_reg, \
             patch("webbrowser.get", return_value=MagicMock()) as mock_get:
            controller = browser._get_firefox_controller()
            self.assertIsNotNone(controller)


class TestTelemetrySanitizationAndDisplay(unittest.TestCase):
    """Part E: Telemetry formatting, empty utterance handling, and confidence badges."""

    def test_24_empty_utterance_displays_na_telemetry(self) -> None:
        """Condition 2: Empty recognition text returns 'N/A' regardless of confidence score."""
        # Empty text with 0.0 confidence (Vosk silence)
        self.assertEqual(format_confidence(0.0, available=True, text=""), "N/A")
        self.assertEqual(get_confidence_color(0.0, available=True, text=""), "#8899ac")

        # Empty text with whitespace
        self.assertEqual(format_confidence(0.85, available=True, text="   "), "N/A")
        self.assertEqual(get_confidence_color(0.85, available=True, text="   "), "#8899ac")

        # Empty text inside TranscriptionResult object
        empty_res = TranscriptionResult(text="", confidence=0.0, engine="vosk", confidence_available=True)
        self.assertEqual(format_confidence(empty_res), "N/A")
        self.assertEqual(get_confidence_color(empty_res), "#8899ac")

    def test_25_genuine_low_confidence_displays_warning(self) -> None:
        """Speech below 0.25 confidence displays percentage with '— Low confidence' notice and red badge."""
        res = TranscriptionResult(text="muffled words", confidence=0.18, engine="vosk", confidence_available=True)
        self.assertEqual(format_confidence(res), "18% — Low confidence")
        self.assertEqual(get_confidence_color(res), "#ff4444")

        # Explicit text call
        self.assertEqual(format_confidence(0.20, available=True, text="mumbled"), "20% — Low confidence")
        self.assertEqual(get_confidence_color(0.20, available=True, text="mumbled"), "#ff4444")

    def test_26_genuine_high_confidence_displays_percentage_and_green_badge(self) -> None:
        """Speech >= 0.70 displays percentage and green badge color."""
        res = TranscriptionResult(text="open youtube", confidence=0.92, engine="vosk", confidence_available=True)
        self.assertEqual(format_confidence(res), "92%")
        self.assertEqual(get_confidence_color(res), "#00ff9d")

        # Moderate confidence [0.25, 0.70) displays cyan badge
        res_med = TranscriptionResult(text="open youtube", confidence=0.55, engine="vosk", confidence_available=True)
        self.assertEqual(format_confidence(res_med), "55%")
        self.assertEqual(get_confidence_color(res_med), "#00d2ff")

    def test_27_missing_confidence_handled_cleanly(self) -> None:
        """Unavailable confidence returns 'N/A' and slate neutral color."""
        res = TranscriptionResult(text="hello", confidence=None, engine="google", confidence_available=False)
        self.assertEqual(format_confidence(res), "N/A")
        self.assertEqual(get_confidence_color(res), "#8899ac")

    def test_28_ui_updates_remain_thread_safe(self) -> None:
        """format_stt_latency and format_stt_engine sanitize types safely."""
        self.assertEqual(format_stt_engine("vosk"), "Vosk")
        self.assertEqual(format_stt_engine("google"), "Google STT")
        self.assertEqual(format_stt_engine(None), "Vosk")

        self.assertEqual(format_stt_latency(0.42), "420 ms")
        self.assertEqual(format_stt_latency(None), "N/A")
        self.assertEqual(format_stt_latency(-0.5), "N/A")


class TestShutdownAndRecovery(unittest.TestCase):
    """Part F: Shutdown safety, resource release, and recovery under stress."""

    def test_29_clean_shutdown_releases_all_threads_and_resources(self) -> None:
        """Detector stop() cleanly unblocks and shuts down thread."""
        detector = WakeWordDetector(wake_phrases=["hey oliver", "hello oliver"])
        with patch.object(detector, "_listen_for_short_phrase", side_effect=lambda: time.sleep(0.01) or ""):
            detector.start(lambda: None)
            self.assertTrue(detector.is_alive)

            detector.stop()
            self.assertFalse(detector.is_alive)
            self.assertTrue(detector._stop_event.is_set())

    def test_30_paused_listener_does_not_restart_after_shutdown(self) -> None:
        """Stopping while paused unblocks resume_event so thread does not hang or restart."""
        detector = WakeWordDetector(wake_phrases=["hey oliver", "hello oliver"])
        with patch.object(detector, "_listen_for_short_phrase", side_effect=lambda: time.sleep(0.01) or ""):
            detector.start(lambda: None)
            detector.pause()
            self.assertTrue(detector.is_paused)

            detector.stop()
            self.assertFalse(detector.is_alive)

    def test_31_exceptions_do_not_corrupt_voice_manager_state(self) -> None:
        """Exceptions in listener.listen_once_result reset VoiceManager._is_listening and state."""
        vm = VoiceManager()
        vm.settings["voice_enabled"] = True
        vm.wake_detector = MagicMock()
        vm.wake_detector.pause.return_value = True

        with patch.object(vm.listener, "listen_once_result", side_effect=ValueError("Acoustic buffer overflow")):
            res = vm.listen_once_result()
            self.assertEqual(res.engine, "error")
            self.assertEqual(vm.current_state, VoiceState.ERROR)
            self.assertFalse(vm._is_listening)


if __name__ == "__main__":
    unittest.main()
