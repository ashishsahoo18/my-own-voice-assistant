"""Comprehensive test suite for Phase 2A.1.3 Stage 2D: Dual Wake Phrase Support.

Covers all 22 required test areas:
1. "Hey OLIVER" recognition
2. "Hello OLIVER" recognition
3. Case-insensitive matching
4. Reasonable whitespace normalization
5. Unrelated speech rejection
6. Partial phrase rejection
7. Ambiguous phrase handling
8. Duplicate activation prevention (cooldown / debounce)
9. Both phrases using the same activation workflow
10. Configuration loading
11. Missing configuration behavior
12. Malformed configuration behavior
13. Vosk structured transcription compatibility
14. Genuine confidence handling
15. Missing confidence handling
16. Existing 0.25 threshold compatibility
17. Legacy string API compatibility
18. Push-to-talk compatibility
19. Listener lifecycle safety
20. VoiceManager integration
21. Thread-safety regression
22. Existing emergency stop compatibility
"""

from __future__ import annotations

import logging
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.config import OliverConfig
from voice.stt.base import TranscriptionResult
from voice.voice_manager import VoiceManager, VoiceState
from voice.wakeword import (
    DEFAULT_WAKE_PHRASES,
    WakeWordDetector,
    normalize_wake_phrase,
)


class TestDualWakePhraseMatching(unittest.TestCase):
    """Test wake phrase matching, tokenization, whitespace, and rejection logic."""

    def setUp(self) -> None:
        self.detector = WakeWordDetector(wake_phrases=["hey oliver", "hello oliver"])

    # -------------------------------------------------------------------------
    # Area 1: "Hey OLIVER" recognition
    # -------------------------------------------------------------------------
    def test_01_hey_oliver_recognition(self) -> None:
        """Verify 'Hey OLIVER' activates wake word detection."""
        self.assertTrue(self.detector._contains_wake_word("Hey OLIVER"))
        self.assertTrue(self.detector._contains_wake_word("hey oliver what time is it"))

    # -------------------------------------------------------------------------
    # Area 2: "Hello OLIVER" recognition
    # -------------------------------------------------------------------------
    def test_02_hello_oliver_recognition(self) -> None:
        """Verify 'Hello OLIVER' activates wake word detection."""
        self.assertTrue(self.detector._contains_wake_word("Hello OLIVER"))
        self.assertTrue(self.detector._contains_wake_word("hello oliver please open google"))

    # -------------------------------------------------------------------------
    # Area 3: Case-insensitive matching
    # -------------------------------------------------------------------------
    def test_03_case_insensitive_matching(self) -> None:
        """Verify wake phrases match across diverse casing combinations."""
        test_cases = [
            "HEY OLIVER",
            "hey oliver",
            "Hey Oliver",
            "hEy OlIvEr",
            "HELLO OLIVER",
            "hello oliver",
            "Hello Oliver",
            "hElLo oLiVeR",
        ]
        for phrase in test_cases:
            self.assertTrue(
                self.detector._contains_wake_word(phrase),
                f"Expected match for case-variant: '{phrase}'",
            )

    # -------------------------------------------------------------------------
    # Area 4: Reasonable whitespace normalization
    # -------------------------------------------------------------------------
    def test_04_whitespace_normalization(self) -> None:
        """Verify leading, trailing, and redundant internal whitespace are normalized."""
        whitespace_cases = [
            "   hey oliver   ",
            "hey    oliver",
            "hello   oliver",
            "  hello   oliver  ",
            "hey\toliver",
            "hello\n oliver",
        ]
        for phrase in whitespace_cases:
            self.assertTrue(
                self.detector._contains_wake_word(phrase),
                f"Expected match with whitespace: '{phrase}'",
            )

    # -------------------------------------------------------------------------
    # Area 5: Unrelated speech rejection
    # -------------------------------------------------------------------------
    def test_05_unrelated_speech_rejection(self) -> None:
        """Verify unrelated everyday speech does NOT activate detection."""
        unrelated_phrases = [
            "what is the weather today",
            "hello world",
            "hey there my friend",
            "play music on youtube",
            "good morning everyone",
            "can you hear me",
            "how are you doing",
        ]
        for phrase in unrelated_phrases:
            self.assertFalse(
                self.detector._contains_wake_word(phrase),
                f"Unrelated phrase '{phrase}' should NOT match",
            )

    # -------------------------------------------------------------------------
    # Area 6: Partial phrase rejection
    # -------------------------------------------------------------------------
    def test_06_partial_phrase_rejection(self) -> None:
        """Verify partial keywords alone do not trigger activation."""
        partials = [
            "oliver",
            "hey",
            "hello",
            "oliver please",
            "just hey",
            "say hello",
        ]
        for phrase in partials:
            self.assertFalse(
                self.detector._contains_wake_word(phrase),
                f"Partial phrase '{phrase}' should NOT match",
            )

    # -------------------------------------------------------------------------
    # Area 7: Ambiguous phrase handling
    # -------------------------------------------------------------------------
    def test_07_ambiguous_phrase_handling(self) -> None:
        """Verify reversed words, scattered words, or lookalikes do NOT trigger activation."""
        ambiguous_cases = [
            "oliver hey",                    # Reversed word order
            "oliver hello",                  # Reversed word order
            "hey friend what is oliver",     # Scattered tokens (non-contiguous)
            "hello to my friend oliver",     # Scattered tokens (non-contiguous)
            "the olive tree",                # Partial word "olive" != "oliver"
            "hey olive",                     # Truncated name
            "they all live here",            # Acoustic phonetic distraction
            "",                              # Empty string
            "   ",                           # Whitespace only
        ]
        for phrase in ambiguous_cases:
            self.assertFalse(
                self.detector._contains_wake_word(phrase),
                f"Ambiguous phrase '{phrase}' should NOT match",
            )


class TestDualWakePhraseLifecycleAndConfidence(unittest.TestCase):
    """Test trigger cooldown, confidence filtering, structured transcription, and lifecycle."""

    def setUp(self) -> None:
        self.mock_engine = MagicMock()
        self.mock_capture = MagicMock()
        self.detector = WakeWordDetector(
            wake_phrases=["hey oliver", "hello oliver"],
            stt_engine=self.mock_engine,
            cooldown_seconds=1.0,
        )
        self.detector.capture = self.mock_capture

    # -------------------------------------------------------------------------
    # Area 8: Duplicate activation prevention
    # -------------------------------------------------------------------------
    def test_08_duplicate_activation_prevention(self) -> None:
        """Verify triggers within cooldown window are debounced and only fire once."""
        callback = MagicMock()
        self.detector._callback = callback

        # First trigger fires callback
        self.detector._trigger_callback()
        self.assertEqual(callback.call_count, 1)

        # Immediate second trigger within cooldown is blocked
        self.detector._trigger_callback()
        self.assertEqual(callback.call_count, 1)

        # Advance time beyond cooldown
        self.detector._last_triggered_at = time.monotonic() - 1.5
        self.detector._trigger_callback()
        self.assertEqual(callback.call_count, 2)

    # -------------------------------------------------------------------------
    # Area 9: Both phrases using the same activation workflow
    # -------------------------------------------------------------------------
    def test_09_both_phrases_use_same_activation_workflow(self) -> None:
        """Verify both 'Hey OLIVER' and 'Hello OLIVER' execute the identical callback."""
        callback = MagicMock()
        self.detector._callback = callback

        # Simulate "hey oliver" detection
        if self.detector._contains_wake_word("hey oliver"):
            self.detector._trigger_callback()

        self.assertEqual(callback.call_count, 1)

        # Reset cooldown and simulate "hello oliver" detection
        self.detector._last_triggered_at = 0.0
        if self.detector._contains_wake_word("hello oliver"):
            self.detector._trigger_callback()

        self.assertEqual(callback.call_count, 2)

    # -------------------------------------------------------------------------
    # Area 13: Vosk structured transcription compatibility
    # -------------------------------------------------------------------------
    def test_13_vosk_structured_transcription_compatibility(self) -> None:
        """Verify _listen_for_short_phrase_result returns and preserves TranscriptionResult."""
        expected_result = TranscriptionResult(
            text="hello oliver",
            confidence=0.88,
            engine="vosk",
            confidence_available=True,
            latency_s=0.35,
        )
        self.mock_engine.transcribe.return_value = expected_result

        result = self.detector._listen_for_short_phrase_result()

        self.assertIsInstance(result, TranscriptionResult)
        self.assertEqual(result.text, "hello oliver")
        self.assertEqual(result.confidence, 0.88)
        self.assertTrue(result.confidence_available)
        self.assertIs(self.detector.last_transcription_result, expected_result)

    # -------------------------------------------------------------------------
    # Area 14: Genuine confidence handling
    # -------------------------------------------------------------------------
    def test_14_genuine_confidence_handling(self) -> None:
        """Verify genuine confidence above threshold is accepted."""
        self.mock_engine.transcribe.return_value = TranscriptionResult(
            text="hey oliver",
            confidence=0.72,
            engine="vosk",
            confidence_available=True,
        )
        heard = self.detector._listen_for_short_phrase()
        self.assertEqual(heard, "hey oliver")

    # -------------------------------------------------------------------------
    # Area 15: Missing confidence handling
    # -------------------------------------------------------------------------
    def test_15_missing_confidence_handling(self) -> None:
        """Verify transcripts without genuine confidence are NOT treated as low-confidence."""
        self.mock_engine.transcribe.return_value = TranscriptionResult(
            text="hello oliver",
            confidence=None,
            engine="fallback_stt",
            confidence_available=False,
        )
        heard = self.detector._listen_for_short_phrase()
        self.assertEqual(heard, "hello oliver")

    # -------------------------------------------------------------------------
    # Area 16: Existing 0.25 threshold compatibility
    # -------------------------------------------------------------------------
    def test_16_confidence_below_point_25_ignored(self) -> None:
        """Verify genuine confidence below 0.25 is rejected per Stage 2A safety rule."""
        self.mock_engine.transcribe.return_value = TranscriptionResult(
            text="hey oliver",
            confidence=0.18,  # Below 0.25 threshold
            engine="vosk",
            confidence_available=True,
        )
        heard = self.detector._listen_for_short_phrase()
        self.assertEqual(heard, "")

    # -------------------------------------------------------------------------
    # Area 17: Legacy string API compatibility
    # -------------------------------------------------------------------------
    def test_17_legacy_string_api_compatibility(self) -> None:
        """Verify _listen_for_short_phrase returns a plain lowercase string."""
        self.mock_engine.transcribe.return_value = TranscriptionResult(
            text="HEY OLIVER",
            confidence=0.90,
            engine="vosk",
            confidence_available=True,
        )
        heard = self.detector._listen_for_short_phrase()
        self.assertIsInstance(heard, str)
        self.assertEqual(heard, "hey oliver")

    # -------------------------------------------------------------------------
    # Area 19: Listener lifecycle safety
    # -------------------------------------------------------------------------
    def test_19_listener_lifecycle_safety(self) -> None:
        """Verify start and stop manage background thread safely without duplicate threads."""
        callback = MagicMock()

        # Stop initially
        self.detector.stop()
        self.assertFalse(self.detector._thread and self.detector._thread.is_alive())

        # Start background listener with blocking run mock to verify single-thread enforcement
        run_event = threading.Event()
        with patch.object(self.detector, "_run", side_effect=lambda: run_event.wait(timeout=2.0)):
            self.detector.start(callback)
            self.assertIsNotNone(self.detector._thread)
            self.assertEqual(self.detector._callback, callback)

            original_thread = self.detector._thread
            self.assertTrue(original_thread.is_alive())

            # Calling start again while running should not spawn new thread
            self.detector.start(callback)
            self.assertIs(self.detector._thread, original_thread)

            # Release run loop and stop
            run_event.set()
            self.detector.stop()
            self.assertTrue(self.detector._stop_event.is_set())


class TestDualWakePhraseConfigurationAndIntegration(unittest.TestCase):
    """Test configuration loading, fallbacks, malformed handling, and VoiceManager integration."""

    # -------------------------------------------------------------------------
    # Area 10: Configuration loading
    # -------------------------------------------------------------------------
    def test_10_configuration_loading(self) -> None:
        """Verify detector and config load dual wake phrases correctly."""
        cfg = OliverConfig()
        self.assertIn("hey oliver", cfg.voice.wake_phrases)
        self.assertIn("hello oliver", cfg.voice.wake_phrases)

        detector = WakeWordDetector(wake_phrases=["hey oliver", "hello oliver"])
        self.assertEqual(detector.wake_phrases, ["hey oliver", "hello oliver"])
        self.assertEqual(detector.wake_word, "hey oliver")

    # -------------------------------------------------------------------------
    # Area 11: Missing configuration behavior
    # -------------------------------------------------------------------------
    def test_11_missing_configuration_behavior(self) -> None:
        """Verify default dual wake phrases are applied when configuration is omitted."""
        detector = WakeWordDetector(wake_phrases=None)
        self.assertEqual(detector.wake_phrases, ["hey oliver", "hello oliver"])

    # -------------------------------------------------------------------------
    # Area 12: Malformed configuration behavior
    # -------------------------------------------------------------------------
    def test_12_malformed_configuration_behavior(self) -> None:
        """Verify malformed configuration falls back safely to default dual wake phrases."""
        malformed_inputs = [
            [],
            ["", "   "],
            None,
            12345,  # type: ignore[arg-type]
        ]
        for bad_input in malformed_inputs:
            detector = WakeWordDetector(wake_phrases=bad_input)
            self.assertEqual(
                detector.wake_phrases,
                list(DEFAULT_WAKE_PHRASES),
                f"Failed safe fallback for malformed input: {bad_input}",
            )

    # -------------------------------------------------------------------------
    # Area 18: Push-to-talk compatibility
    # -------------------------------------------------------------------------
    def test_18_push_to_talk_compatibility(self) -> None:
        """Verify push-to-talk operation remains functional alongside wake word detector."""
        with (
            patch("voice.voice_manager.VoiceListener") as mock_listener_cls,
            patch("voice.voice_manager.VoiceSpeaker"),
            patch("voice.voice_manager.WakeWordDetector"),
        ):
            mock_listener = MagicMock()
            mock_listener.listen_once_result.return_value = TranscriptionResult(
                text="typed or ptt command",
                confidence=0.92,
                engine="vosk",
                confidence_available=True,
            )
            mock_listener_cls.return_value = mock_listener

            vm = VoiceManager()
            # Push-to-talk invokes listen_once directly
            text = vm.listen_once()
            self.assertEqual(text, "typed or ptt command")
            mock_listener.listen_once_result.assert_called_once()

    # -------------------------------------------------------------------------
    # Area 20: VoiceManager integration
    # -------------------------------------------------------------------------
    def test_20_voice_manager_integration(self) -> None:
        """Verify VoiceManager exposes wake_phrases and starts/stops wake detector."""
        with (
            patch("voice.voice_manager.VoiceListener"),
            patch("voice.voice_manager.VoiceSpeaker"),
            patch.object(VoiceManager, "_write_settings"),
        ):
            vm = VoiceManager()
            self.assertIn("hey oliver", vm.wake_phrases)
            self.assertIn("hello oliver", vm.wake_phrases)

            # Test updating wake phrases
            vm.set_wake_phrases(["hey oliver", "hello oliver", "ayra"])
            self.assertEqual(vm.wake_phrases, ["hey oliver", "hello oliver", "ayra"])
            self.assertEqual(vm.settings.get("wake_word"), "hey oliver")

    # -------------------------------------------------------------------------
    # Area 21: Thread-safety regression
    # -------------------------------------------------------------------------
    def test_21_thread_safety_concurrent_access(self) -> None:
        """Verify set_wake_phrases and _contains_wake_word can run concurrently without crash."""
        detector = WakeWordDetector()
        errors = []

        def reader():
            for _ in range(50):
                try:
                    detector._contains_wake_word("hello oliver")
                    detector._contains_wake_word("unrelated text")
                    _ = detector.wake_phrases
                    _ = detector.wake_word
                except Exception as exc:
                    errors.append(exc)

        def writer():
            for i in range(50):
                try:
                    if i % 2 == 0:
                        detector.set_wake_phrases(["hey oliver", "hello oliver"])
                    else:
                        detector.set_wake_phrases(["hello oliver", "hey oliver"])
                except Exception as exc:
                    errors.append(exc)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        self.assertEqual(len(errors), 0, f"Thread safety errors: {errors}")

    # -------------------------------------------------------------------------
    # Area 22: Existing emergency stop compatibility
    # -------------------------------------------------------------------------
    def test_22_emergency_stop_compatibility(self) -> None:
        """Verify barge_in and stop_speaking stop speech without disrupting wake detector."""
        with (
            patch("voice.voice_manager.VoiceListener"),
            patch("voice.voice_manager.VoiceSpeaker") as mock_speaker_cls,
            patch("voice.voice_manager.WakeWordDetector") as mock_detector_cls,
        ):
            mock_speaker = MagicMock()
            mock_speaker_cls.return_value = mock_speaker
            mock_detector = MagicMock()
            mock_detector_cls.return_value = mock_detector

            vm = VoiceManager()
            vm.stop_speaking()

            # Speaker barge_in must be called (emergency stop)
            mock_speaker.barge_in.assert_called_once()
            # Wake detector must NOT be stopped during speech barge_in
            mock_detector.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
