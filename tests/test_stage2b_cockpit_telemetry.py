"""Unit and integration tests for Phase 2A.1.3 Stage 2B: Cockpit UI Metadata Display & Live Voice Telemetry."""

from __future__ import annotations

import math
import threading
from unittest.mock import MagicMock, patch

import pytest

from ui.telemetry_utils import (
    format_confidence,
    format_stt_engine,
    format_stt_latency,
    get_confidence_color,
    get_status_color,
)
from voice.stt.base import TranscriptionResult
from voice.voice_manager import VoiceManager


# =============================================================================
# Part 1: Confidence Formatting & Sanitization Tests (Feature B)
# =============================================================================

class TestConfidenceDisplayFormatting:
    """Tests covering transcription confidence formatting for the Cockpit UI."""

    def test_01_valid_confidence_percentage(self):
        """Valid confidence in [0.25, 1.0] formats as percentage."""
        assert format_confidence(0.87, available=True) == "87%"
        assert format_confidence(0.999, available=True) == "100%"
        assert format_confidence(0.25, available=True) == "25%"
        assert format_confidence(1.0, available=True) == "100%"

    def test_02_unavailable_confidence_displays_na(self):
        """Unavailable confidence score returns 'N/A'."""
        assert format_confidence(None, available=False) == "N/A"
        assert format_confidence(None, available=True) == "N/A"
        assert format_confidence(0.85, available=False) == "N/A"

    def test_03_low_confidence_distinguished_with_label(self):
        """Confidence below 0.25 displays percentage with '— Low confidence' notice."""
        assert format_confidence(0.18, available=True) == "18% — Low confidence"
        assert format_confidence(0.05, available=True) == "5% — Low confidence"
        assert format_confidence(0.0, available=True) == "0% — Low confidence"
        assert format_confidence(0.249, available=True) == "25% — Low confidence"

    def test_04_boolean_confidence_rejected(self):
        """Booleans True and False are strictly rejected and return 'N/A'."""
        assert format_confidence(True, available=True) == "N/A"
        assert format_confidence(False, available=True) == "N/A"
        assert format_confidence(True, available=False) == "N/A"

    def test_05_nan_and_infinity_rejected(self):
        """NaN and ±Inf floats are rejected and return 'N/A'."""
        assert format_confidence(float("nan"), available=True) == "N/A"
        assert format_confidence(float("inf"), available=True) == "N/A"
        assert format_confidence(float("-inf"), available=True) == "N/A"

    def test_06_out_of_range_and_invalid_types_rejected(self):
        """Negative scores, scores > 1.0, strings, and collections return 'N/A'."""
        assert format_confidence(-0.5, available=True) == "N/A"
        assert format_confidence(1.5, available=True) == "N/A"
        assert format_confidence("0.85", available=True) == "N/A"  # String type rejected
        assert format_confidence("not_numeric", available=True) == "N/A"
        assert format_confidence({"conf": 0.8}, available=True) == "N/A"
        assert format_confidence([0.8], available=True) == "N/A"

    def test_07_confidence_color_mapping(self):
        """Confidence color indicates high (green), moderate (cyan), low (red), and N/A (slate)."""
        assert get_confidence_color(0.85, available=True) == "#00ff9d"  # High
        assert get_confidence_color(0.50, available=True) == "#00d2ff"  # Moderate
        assert get_confidence_color(0.18, available=True) == "#ff4444"  # Low (< 0.25)
        assert get_confidence_color(None, available=False) == "#8899ac"  # N/A
        assert get_confidence_color(True, available=True) == "#8899ac"   # Rejected bool


# =============================================================================
# Part 2: STT Latency Formatting Tests (Feature C)
# =============================================================================

class TestSTTLatencyFormatting:
    """Tests covering STT latency duration formatting for the Cockpit UI."""

    def test_01_valid_latency_in_milliseconds(self):
        """Positive float duration in seconds converts to round milliseconds string."""
        assert format_stt_latency(0.420) == "420 ms"
        assert format_stt_latency(1.250) == "1250 ms"
        assert format_stt_latency(0.050) == "50 ms"

    def test_02_unavailable_and_zero_latency_displays_na(self):
        """Missing, None, or zero duration displays 'N/A' (distinguished from measured 0)."""
        assert format_stt_latency(None) == "N/A"
        assert format_stt_latency(0.0) == "N/A"
        assert format_stt_latency(0) == "N/A"

    def test_03_invalid_types_and_bounds_rejected(self):
        """Booleans, negative durations, NaN, and Inf return 'N/A'."""
        assert format_stt_latency(True) == "N/A"
        assert format_stt_latency(False) == "N/A"
        assert format_stt_latency(-0.5) == "N/A"
        assert format_stt_latency(float("nan")) == "N/A"
        assert format_stt_latency(float("inf")) == "N/A"
        assert format_stt_latency("fast") == "N/A"


# =============================================================================
# Part 3: STT Engine & Status Tests (Feature A)
# =============================================================================

class TestSTTEngineAndStatus:
    """Tests covering active STT engine identification and status display."""

    def test_01_engine_name_formatting(self):
        """Engine names format correctly for display."""
        assert format_stt_engine("vosk") == "Vosk"
        assert format_stt_engine("local_first_hybrid") == "Vosk"
        assert format_stt_engine("google") == "Google STT"
        assert format_stt_engine("") == "Vosk"
        assert format_stt_engine(None) == "Vosk"

    def test_02_status_color_mapping(self):
        """Voice states map to expected futuristic HUD hex colors."""
        assert get_status_color("READY") == "#00ff9d"
        assert get_status_color("Status: READY") == "#00ff9d"
        assert get_status_color("LISTENING") == "#00d2ff"
        assert get_status_color("PROCESSING") == "#ffcf36"
        assert get_status_color("SPEAKING") == "#36b6ff"
        assert get_status_color("ERROR") == "#ff4444"
        assert get_status_color("DISABLED") == "#64748b"
        assert get_status_color("UNAVAILABLE") == "#64748b"

    def test_03_voice_manager_stt_properties(self, tmp_path):
        """VoiceManager exposes stt_engine_name and is_stt_available properties."""
        cfg = tmp_path / "settings.json"
        # Patch hardware-dependent components to prevent COM/audio side-effects
        # that would pollute subsequent CustomTkinter tests in the same process.
        with (
            patch("voice.voice_manager.VoiceListener"),
            patch("voice.voice_manager.VoiceSpeaker"),
            patch("voice.voice_manager.WakeWordDetector"),
        ):
            vm = VoiceManager(settings_path=cfg)

        assert vm.stt_engine_name == "Vosk"
        assert isinstance(vm.is_stt_available, bool)

        # When voice is disabled in settings
        vm.settings["voice_enabled"] = False
        assert vm.is_stt_available is False


# =============================================================================
# Part 4: UI Thread Safety & Event Bridge (Feature E)
# =============================================================================

class TestUIThreadSafetyAndIntegration:
    """Tests covering thread-safe dispatching and event bridge routing."""

    def test_01_background_call_dispatches_via_event_bridge(self):
        """Calling update_voice_telemetry from background thread enqueues to event bridge."""
        from ui.chat import CommandConsolePanel

        mock_bridge = MagicMock()
        mock_bridge._main_thread_id = 12345  # Distinct from current thread

        panel = CommandConsolePanel.__new__(CommandConsolePanel)
        panel.event_bridge = mock_bridge

        mock_result = TranscriptionResult(text="test audio", confidence=0.88, engine="vosk", latency_s=0.35)

        # Execute on current thread (which is != 12345)
        panel.update_voice_telemetry(result=mock_result, status="READY")

        # Verify it was safely posted to event bridge, NOT executed directly
        mock_bridge.post.assert_called_once_with(
            panel.update_voice_telemetry,
            mock_result,
            "READY",
            None,
            None,
        )

    def test_02_main_thread_applies_telemetry_directly(self):
        """Calling update_voice_telemetry from main thread updates StringVars directly."""
        from ui.chat import CommandConsolePanel

        current_thread_id = threading.get_ident()
        mock_bridge = MagicMock()
        mock_bridge._main_thread_id = current_thread_id

        panel = CommandConsolePanel.__new__(CommandConsolePanel)
        panel.event_bridge = mock_bridge

        # Mock StringVars
        panel.telemetry_engine_var = MagicMock()
        panel.telemetry_status_var = MagicMock()
        panel.telemetry_conf_var = MagicMock()
        panel.telemetry_latency_var = MagicMock()
        panel.transcript_var = MagicMock()

        mock_result = TranscriptionResult(
            text="open browser",
            confidence=0.92,
            engine="vosk",
            latency_s=0.450,
            confidence_available=True,
        )

        panel.update_voice_telemetry(result=mock_result, status="READY", transcript="open browser")

        # Verify StringVars were updated
        panel.telemetry_engine_var.set.assert_called_with("STT Engine: Vosk")
        panel.telemetry_status_var.set.assert_called_with("Status: READY")
        panel.telemetry_conf_var.set.assert_called_with("Confidence: 92%")
        panel.telemetry_latency_var.set.assert_called_with("STT Latency: 450 ms")
        panel.transcript_var.set.assert_called_with("open browser")

        # Event bridge post was NOT called because caller was on the main thread
        mock_bridge.post.assert_not_called()

    def test_03_error_state_handling(self):
        """Error status updates status badge to ERROR and resets metrics to N/A."""
        from ui.chat import CommandConsolePanel

        current_thread_id = threading.get_ident()
        mock_bridge = MagicMock()
        mock_bridge._main_thread_id = current_thread_id

        panel = CommandConsolePanel.__new__(CommandConsolePanel)
        panel.event_bridge = mock_bridge

        panel.telemetry_engine_var = MagicMock()
        panel.telemetry_status_var = MagicMock()
        panel.telemetry_conf_var = MagicMock()
        panel.telemetry_latency_var = MagicMock()
        panel.transcript_var = MagicMock()

        panel.update_voice_telemetry(
            error="Microphone device disconnected",
            transcript="Microphone access error. Please check permissions.",
        )

        panel.telemetry_status_var.set.assert_called_with("Status: ERROR")
        panel.telemetry_conf_var.set.assert_called_with("Confidence: N/A")
        panel.telemetry_latency_var.set.assert_called_with("STT Latency: N/A")
        panel.transcript_var.set.assert_called_with("Microphone access error. Please check permissions.")

    def test_04_backward_compatibility_preserved(self, tmp_path):
        """VoiceManager.listen_once() still returns plain string, updating last_transcription_result."""
        cfg = tmp_path / "compat_settings.json"
        # Patch hardware-dependent components to prevent COM/audio side-effects
        # that would pollute subsequent CustomTkinter tests in the same process.
        with (
            patch("voice.voice_manager.VoiceListener"),
            patch("voice.voice_manager.VoiceSpeaker"),
            patch("voice.voice_manager.WakeWordDetector"),
        ):
            vm = VoiceManager(settings_path=cfg)

        mock_result = TranscriptionResult(
            text="what time is it",
            confidence=0.85,
            engine="vosk",
            latency_s=0.280,
            confidence_available=True,
        )
        vm.listener.listen_once_result = MagicMock(return_value=mock_result)

        text = vm.listen_once()
        assert isinstance(text, str)
        assert text == "what time is it"
        assert vm.last_transcription_result == mock_result
        assert vm.last_transcription_result.confidence == pytest.approx(0.85)
        assert vm.last_transcription_result.latency_s == pytest.approx(0.280)
