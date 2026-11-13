"""Unit and regression tests for Phase 2A.1.3 Stage 2A: Vosk confidence reliability & structured transcription preservation."""

from __future__ import annotations

import json
import math
from unittest.mock import MagicMock, patch

import pytest

from voice.listener import VoiceListener
from voice.stt.base import TranscriptionResult
from voice.stt.vosk_engine import VoskSTTEngine
from voice.voice_manager import VoiceManager


# -----------------------------------------------------------------------------
# Part 1: Confidence Calculation & Sanitization (10 Scenarios)
# -----------------------------------------------------------------------------

class TestVoskConfidenceScenarios:
    """Tests covering the 10 confidence calculation and validation scenarios."""

    @pytest.fixture
    def engine(self):
        engine = VoskSTTEngine()
        engine.model_loaded = True
        return engine

    def test_01_valid_word_confidences(self, engine):
        """Scenario 1: Valid word-level confidences are averaged correctly."""
        raw_json = json.dumps({
            "text": "open youtube",
            "result": [
                {"word": "open", "conf": 0.8},
                {"word": "youtube", "conf": 0.9},
            ],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "open youtube"
        assert res.confidence == pytest.approx(0.85, rel=1e-3)
        assert res.confidence_available is True

    def test_02_missing_word_level_confidence(self, engine):
        """Scenario 2: Valid text but missing word tokens/confidences sets confidence=None, available=False."""
        raw_json = json.dumps({
            "text": "open youtube",
            "result": [],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "open youtube"
        assert res.confidence is None
        assert res.confidence_available is False

    def test_03_empty_text(self, engine):
        """Scenario 3: Empty text yields confidence=0.0 and available=True."""
        raw_json = json.dumps({"text": ""})
        res = engine._parse_vosk_result(raw_json)
        assert res.text == ""
        assert res.confidence == 0.0
        assert res.confidence_available is True

    def test_04_invalid_confidence_types(self, engine):
        """Scenario 4: Non-numeric confidence types (strings, None) are ignored."""
        raw_json = json.dumps({
            "text": "test audio",
            "result": [
                {"word": "test", "conf": "not_a_number"},
                {"word": "audio", "conf": None},
            ],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "test audio"
        assert res.confidence is None
        assert res.confidence_available is False

    def test_05_negative_confidence_values_ignored(self, engine):
        """Scenario 5: Negative confidence values are rejected."""
        raw_json = json.dumps({
            "text": "negative check",
            "result": [
                {"word": "negative", "conf": -0.5},
                {"word": "check", "conf": 0.6},
            ],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "negative check"
        # Only the valid 0.6 should be counted
        assert res.confidence == pytest.approx(0.6, rel=1e-3)
        assert res.confidence_available is True

    def test_06_values_greater_than_one_ignored(self, engine):
        """Scenario 6: Confidence values > 1.0 are rejected."""
        raw_json = json.dumps({
            "text": "overflow check",
            "result": [
                {"word": "overflow", "conf": 1.5},
                {"word": "check", "conf": 0.7},
            ],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "overflow check"
        assert res.confidence == pytest.approx(0.7, rel=1e-3)
        assert res.confidence_available is True

    def test_07_nan_confidence_ignored(self, engine):
        """Scenario 7: NaN confidence values are rejected."""
        raw_dict = {
            "text": "nan test",
            "result": [
                {"word": "nan", "conf": float("nan")},
                {"word": "test", "conf": 0.75},
            ],
        }
        res = engine._parse_vosk_dict(raw_dict)
        assert res.text == "nan test"
        assert res.confidence == pytest.approx(0.75, rel=1e-3)
        assert res.confidence_available is True

    def test_08_infinite_confidence_ignored(self, engine):
        """Scenario 8: Infinite confidence values are rejected."""
        raw_dict = {
            "text": "inf test",
            "result": [
                {"word": "inf", "conf": float("inf")},
                {"word": "test", "conf": float("-inf")},
            ],
        }
        res = engine._parse_vosk_dict(raw_dict)
        assert res.text == "inf test"
        assert res.confidence is None
        assert res.confidence_available is False

    def test_09_multiple_valid_word_confidences_arithmetic_mean(self, engine):
        """Scenario 9: Multiple valid word tokens are combined as exact arithmetic mean."""
        raw_json = json.dumps({
            "text": "one two three four",
            "result": [
                {"word": "one", "conf": 0.4},
                {"word": "two", "conf": 0.6},
                {"word": "three", "conf": 0.8},
                {"word": "four", "conf": 1.0},
            ],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "one two three four"
        assert res.confidence == pytest.approx(0.7, rel=1e-4)
        assert res.confidence_available is True

    def test_10_no_artificial_one_dot_zero(self, engine):
        """Scenario 10: Valid text with no word confidences NEVER manufactures 1.0."""
        raw_json = json.dumps({"text": "hello oliver"})
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "hello oliver"
        assert res.confidence is not 1.0
        assert res.confidence is None
        assert res.confidence_available is False

    def test_11_boolean_confidence_rejected_in_vosk_engine(self, engine):
        """Defect B: Boolean confidence values in word tokens are rejected as non-numeric."""
        raw_json = json.dumps({
            "text": "boolean check",
            "result": [
                {"word": "boolean", "conf": True},
                {"word": "check", "conf": False},
            ],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "boolean check"
        assert res.confidence is None
        assert res.confidence_available is False

    def test_12_mixed_boolean_and_valid_word_confidence(self, engine):
        """Defect B: Valid confidences are averaged while boolean tokens are safely skipped."""
        raw_json = json.dumps({
            "text": "one two",
            "result": [
                {"word": "one", "conf": True},
                {"word": "two", "conf": 0.8},
            ],
        })
        res = engine._parse_vosk_result(raw_json)
        assert res.text == "one two"
        assert res.confidence == pytest.approx(0.8, rel=1e-3)
        assert res.confidence_available is True


# -----------------------------------------------------------------------------
# Part 2: Structured Result Preservation (7 Scenarios)
# -----------------------------------------------------------------------------

class TestStructuredResultPreservation:
    """Tests covering structured TranscriptionResult metadata preservation."""

    def test_01_text_preserved_in_transcription_result(self):
        """Metadata scenario 1: Spoken text is preserved exactly."""
        res = TranscriptionResult(text="open settings", confidence=0.82)
        assert res.text == "open settings"

    def test_02_confidence_preserved_when_available(self):
        """Metadata scenario 2: Available confidence is preserved."""
        res = TranscriptionResult(text="search python", confidence=0.91, confidence_available=True)
        assert res.confidence == pytest.approx(0.91)
        assert res.confidence_available is True

    def test_03_missing_confidence_marked_unavailable(self):
        """Metadata scenario 3: Unavailable confidence sets confidence_available=False."""
        res = TranscriptionResult(text="check calendar", confidence=None, confidence_available=False)
        assert res.confidence is None
        assert res.confidence_available is False

    def test_04_engine_name_preserved(self):
        """Metadata scenario 4: STT engine identifier is preserved."""
        res = TranscriptionResult(text="test", engine="vosk")
        assert res.engine == "vosk"

    def test_05_recognition_status_and_details_preserved(self):
        """Metadata scenario 5: is_offline, latency, and details dict are preserved."""
        res = TranscriptionResult(
            text="partial speech",
            is_offline=True,
            latency_s=0.123,
            engine="vosk",
            details={"raw": {"partial": "partial speech"}},
        )
        assert res.is_offline is True
        assert res.latency_s == 0.123
        assert res.details == {"raw": {"partial": "partial speech"}}

    def test_06_listen_once_backward_compatibility_string(self):
        """Metadata scenario 6: listen_once() on listener returns a plain string."""
        listener = VoiceListener()
        mock_result = TranscriptionResult(
            text="what time is it",
            confidence=0.88,
            confidence_available=True,
            engine="vosk",
        )
        listener.listen_once_result = MagicMock(return_value=mock_result)

        returned_val = listener.listen_once()
        assert isinstance(returned_val, str)
        assert returned_val == "what time is it"

    def test_07_malformed_json_handled_safely(self):
        """Metadata scenario 7: Malformed JSON handled gracefully without crashing."""
        engine = VoskSTTEngine()
        malformed = "NOT_JSON_<<<>>>"
        res = engine._parse_vosk_result(malformed)
        assert isinstance(res, TranscriptionResult)
        assert res.text == ""
        assert res.confidence is None
        assert res.confidence_available is False


# -----------------------------------------------------------------------------
# Part 3: Pipeline Integration & Threshold Logic (Regression Scenarios)
# -----------------------------------------------------------------------------

class TestVoicePipelineIntegration:
    """Integration and threshold logic tests for Stage 2A."""

    def test_listener_filters_low_confidence_when_available(self):
        """Low confidence (<0.25) is filtered when confidence is available in listen_once()."""
        listener = VoiceListener()
        listener.capture.capture_audio = MagicMock(return_value=MagicMock())

        # Mock STT engine returning low confidence
        low_conf_result = TranscriptionResult(
            text="garbled noise",
            confidence=0.15,
            confidence_available=True,
            engine="vosk",
        )
        listener.stt_engine.transcribe = MagicMock(return_value=low_conf_result)

        # Raw result retains structured confidence
        raw_res = listener.listen_once_result()
        assert raw_res.text == "garbled noise"
        assert raw_res.confidence == 0.15

        # Backward-compatible listen_once filters low-confidence out
        str_out = listener.listen_once()
        assert str_out == ""

    def test_listener_does_not_filter_valid_text_when_confidence_unavailable(self):
        """Valid text is NOT filtered out when confidence is unavailable (None)."""
        listener = VoiceListener()
        listener.capture.capture_audio = MagicMock(return_value=MagicMock())

        unavail_conf_result = TranscriptionResult(
            text="open browser",
            confidence=None,
            confidence_available=False,
            engine="vosk",
        )
        listener.stt_engine.transcribe = MagicMock(return_value=unavail_conf_result)

        raw_res = listener.listen_once_result()
        assert raw_res.text == "open browser"
        assert raw_res.confidence is None
        assert raw_res.confidence_available is False

        str_out = listener.listen_once()
        assert str_out == "open browser"

    def test_voice_manager_listen_once_result_and_backward_compat(self, tmp_path):
        """VoiceManager stores last_transcription_result and returns str from listen_once."""
        # Use custom config path to avoid touching user voice_settings.json
        settings_file = tmp_path / "test_settings.json"
        vm = VoiceManager(settings_path=settings_file)

        mock_result = TranscriptionResult(
            text="navigate to dashboard",
            confidence=0.92,
            confidence_available=True,
            engine="vosk",
        )
        vm.listener.listen_once_result = MagicMock(return_value=mock_result)

        # 1. Test listen_once_result
        res = vm.listen_once_result()
        assert res == mock_result
        assert vm.last_transcription_result == mock_result

        # 2. Test listen_once (backward compatibility)
        str_out = vm.listen_once()
        assert isinstance(str_out, str)
        assert str_out == "navigate to dashboard"
        assert vm.last_transcription_result == mock_result

    def test_transcription_result_sanitization_post_init(self):
        """Direct TranscriptionResult instantiation sanitizes invalid numeric bounds."""
        res_neg = TranscriptionResult(text="hi", confidence=-0.1)
        assert res_neg.confidence is None
        assert res_neg.confidence_available is False

        res_gt1 = TranscriptionResult(text="hi", confidence=1.2)
        assert res_gt1.confidence is None
        assert res_gt1.confidence_available is False

        res_nan = TranscriptionResult(text="hi", confidence=float("nan"))
        assert res_nan.confidence is None
        assert res_nan.confidence_available is False

    def test_transcription_result_rejects_booleans(self):
        """Defect B: Boolean confidence values in TranscriptionResult are rejected."""
        res_true = TranscriptionResult(text="true test", confidence=True)
        assert res_true.confidence is None
        assert res_true.confidence_available is False

        res_false = TranscriptionResult(text="false test", confidence=False)
        assert res_false.confidence is None
        assert res_false.confidence_available is False

        # Numeric 0.0 and 1.0 are valid and preserved
        res_zero = TranscriptionResult(text="zero test", confidence=0.0)
        assert res_zero.confidence == 0.0
        assert res_zero.confidence_available is True

        res_one = TranscriptionResult(text="one test", confidence=1.0)
        assert res_one.confidence == 1.0
        assert res_one.confidence_available is True

    def test_voice_manager_disabled_branch_no_crash(self, tmp_path):
        """Defect A: VoiceManager returns valid TranscriptionResult when voice is disabled."""
        settings_file = tmp_path / "disabled_settings.json"
        vm = VoiceManager(settings_path=settings_file)
        vm.settings["voice_enabled"] = False

        res = vm.listen_once_result()
        assert isinstance(res, TranscriptionResult)
        assert res.text == ""
        assert res.engine == "disabled"
        assert res.confidence == 0.0
        assert res.confidence_available is True

        # Plain string backward compatibility
        str_res = vm.listen_once()
        assert str_res == ""

    def test_voice_manager_busy_branch_no_crash(self, tmp_path):
        """Defect A: VoiceManager returns valid TranscriptionResult when voice is busy."""
        settings_file = tmp_path / "busy_settings.json"
        vm = VoiceManager(settings_path=settings_file)
        vm._is_listening = True

        res = vm.listen_once_result()
        assert isinstance(res, TranscriptionResult)
        assert res.text == ""
        assert res.engine == "busy"
        assert res.confidence == 0.0
        assert res.confidence_available is True

        str_res = vm.listen_once()
        assert str_res == ""

    def test_voice_manager_listener_exception_branch_no_crash(self, tmp_path):
        """Defect A: VoiceManager handles listener exceptions without TypeError crash."""
        from voice.states import VoiceState

        settings_file = tmp_path / "error_settings.json"
        vm = VoiceManager(settings_path=settings_file)
        vm.listener.listen_once_result = MagicMock(side_effect=RuntimeError("Microphone unplugged"))

        res = vm.listen_once_result()
        assert isinstance(res, TranscriptionResult)
        assert res.text == ""
        assert res.engine == "error"
        assert res.details == {"error": "Microphone unplugged"}
        assert vm.state_machine.current_state == VoiceState.ERROR

        # Test string return under exception
        str_res = vm.listen_once()
        assert str_res == ""
        assert vm.state_machine.current_state == VoiceState.ERROR
