"""Comprehensive unit and regression tests for OLIVER 2.0 Real-Time Audio / Voice Pipeline (Phase 7)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import speech_recognition as sr

from ai.assistant import AshishAssistant
from core.config import OliverConfig, get_config, reload_config
from execution.engine import ExecutionEngine
from execution.request import TaskRequest
from security.confirmation import ConfirmationManager, get_confirmation_manager
from security.kill_switch import KillSwitch
from security.policy_engine import PolicyEngine
from security.sandbox import PathSandbox
from voice.audio_capture import AudioCapture, MicrophoneError
from voice.confirmation_bridge import VoiceConfirmationBridge
from voice.language import LanguageStatus, VoiceLanguage
from voice.listener import VoiceListener
from voice.speaker import VoiceSpeaker
from voice.states import VoiceState, VoiceStateMachine
from voice.stt.base import SpeechToTextEngine, TranscriptionResult
from voice.stt.google_engine import GoogleSTTEngine
from voice.stt.local_first import LocalFirstSTTEngine
from voice.stt.vosk_engine import VoskSTTEngine
from voice.vad import VoiceActivityDetector
from voice.voice_manager import VoiceManager


class DummySTTEngine(SpeechToTextEngine):
    """Predictable mock STT engine for test isolation."""

    def __init__(self, transcript: str = "open calculator", available: bool = True, offline: bool = True) -> None:
        self._transcript = transcript
        self._available = available
        self._offline = offline

    @property
    def name(self) -> str:
        return "dummy_engine"

    @property
    def is_offline(self) -> bool:
        return self._offline

    def is_available(self) -> bool:
        return self._available

    def transcribe(self, audio_data: sr.AudioData, language: str = "en") -> TranscriptionResult:
        if not self._available:
            raise RuntimeError("Engine not available")
        return TranscriptionResult(
            text=self._transcript,
            confidence=1.0,
            engine=self.name,
            is_offline=self._offline,
            latency_s=0.05,
            external_service_disclosed=not self._offline,
        )


class VoicePipelineTests(unittest.TestCase):
    """Test suite for Phase 7 modular voice pipeline components."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.settings_file = self.tmp_path / "voice_settings.json"
        self.orig_router_mode = get_config().router_mode

    def tearDown(self) -> None:
        get_config().router_mode = self.orig_router_mode
        reload_config()
        self.tmp_dir.cleanup()

    # --- 1. Voice State Machine ---
    def test_voice_state_machine_transitions_and_observers(self) -> None:
        sm = VoiceStateMachine(initial_state=VoiceState.READY)
        observed = []

        def on_change(state: VoiceState, detail: str | None) -> None:
            observed.append((state, detail))

        sm.add_listener(on_change)

        sm.transition_to(VoiceState.LISTENING)
        sm.transition_to(VoiceState.PROCESSING, detail="speech_captured")
        sm.transition_to(VoiceState.EXECUTING)
        sm.transition_to(VoiceState.SPEAKING)
        sm.transition_to(VoiceState.ERROR, detail="mic_disconnected")
        sm.transition_to(VoiceState.READY)

        self.assertEqual(sm.current_state, VoiceState.READY)
        self.assertEqual(len(observed), 6)
        self.assertEqual(observed[0], (VoiceState.LISTENING, None))
        self.assertEqual(observed[1], (VoiceState.PROCESSING, "speech_captured"))
        self.assertEqual(observed[4], (VoiceState.ERROR, "mic_disconnected"))

        # Test observer removal
        sm.remove_listener(on_change)
        sm.transition_to(VoiceState.LISTENING)
        self.assertEqual(len(observed), 6)

    # --- 2. Audio Capture & Hardware Lifecycle ---
    def test_audio_capture_lifecycle_and_hardware_error_handling(self) -> None:
        capture = AudioCapture()
        self.assertFalse(capture.is_active)

        # Mock successful open/close
        mock_source = MagicMock()
        mock_mic = MagicMock()
        mock_mic.__enter__.return_value = mock_source
        capture._microphone = mock_mic

        src = capture.open_stream()
        self.assertTrue(capture.is_active)
        self.assertEqual(src, mock_source)

        capture.close_stream()
        self.assertFalse(capture.is_active)

        # Mock hardware/OS error
        failing_capture = AudioCapture()
        fail_mic = MagicMock()
        fail_mic.__enter__.side_effect = OSError("Device disconnected / unplugged")
        failing_capture._microphone = fail_mic

        with self.assertRaises(MicrophoneError):
            failing_capture.open_stream()
        self.assertFalse(failing_capture.is_active)

    # --- 3. Voice Activity Detection (VAD) ---
    def test_vad_energy_calculation_and_calibration(self) -> None:
        vad = VoiceActivityDetector(energy_threshold=200.0)

        # Silence frame (all zeroes)
        silence_pcm = b"\x00\x00" * 512
        self.assertEqual(vad.calculate_energy(silence_pcm), 0.0)
        self.assertFalse(vad.is_speech(silence_pcm))

        # Loud synthetic frame (high amplitude 16-bit PCM: ~16384 amplitude)
        loud_pcm = (b"\x00\x40" + b"\x00\xc0") * 256
        energy = vad.calculate_energy(loud_pcm)
        self.assertGreater(energy, 200.0)
        self.assertTrue(vad.is_speech(loud_pcm))

        # Calibration
        ambient = [silence_pcm, silence_pcm]
        thresh = vad.calibrate(ambient)
        self.assertGreater(thresh, 0.0)

    # --- 4. Local Offline STT (Vosk) ---
    def test_vosk_engine_availability_and_transcription(self) -> None:
        vosk_engine = VoskSTTEngine()
        self.assertEqual(vosk_engine.name, "vosk_local")
        self.assertTrue(vosk_engine.is_offline)

        # Vosk model was downloaded and cached in setup
        self.assertTrue(vosk_engine.is_available())

        # Test transcription with mock audio data
        mock_audio = MagicMock(spec=sr.AudioData)
        # Empty/silence PCM data
        mock_audio.get_raw_data.return_value = b"\x00\x00" * 16000

        res = vosk_engine.transcribe(mock_audio)
        self.assertIsInstance(res, TranscriptionResult)
        self.assertTrue(res.is_offline)
        self.assertFalse(res.external_service_disclosed)
        self.assertGreaterEqual(res.latency_s, 0.0)

    # --- 5. External STT Fallback & Privacy Disclosure ---
    def test_google_engine_external_disclosure(self) -> None:
        mock_recognizer = MagicMock()
        mock_recognizer.recognize_google.return_value = "hello assistant"

        engine = GoogleSTTEngine(recognizer=mock_recognizer)
        self.assertFalse(engine.is_offline)

        mock_audio = MagicMock(spec=sr.AudioData)
        with self.assertLogs("voice.stt.google_engine", level="WARNING") as log_cm:
            res = engine.transcribe(mock_audio, language="en-US")

        self.assertEqual(res.text, "hello assistant")
        self.assertFalse(res.is_offline)
        self.assertTrue(res.external_service_disclosed)
        # Verify privacy disclosure was logged
        self.assertTrue(any("PRIVACY DISCLOSURE" in msg for msg in log_cm.output))

    # --- 6. Local-First Hybrid Fallback Logic ---
    def test_local_first_prefers_local_and_falls_back_when_permitted(self) -> None:
        mock_local = MagicMock(spec=SpeechToTextEngine)
        mock_local.name = "mock_local"
        mock_local.is_available.return_value = True
        mock_local.transcribe.return_value = TranscriptionResult(
            text="local recognized command",
            is_offline=True,
            external_service_disclosed=False,
        )

        mock_fallback = MagicMock(spec=SpeechToTextEngine)
        mock_fallback.name = "mock_cloud"
        mock_fallback.is_available.return_value = True
        mock_fallback.transcribe.return_value = TranscriptionResult(
            text="fallback command",
            is_offline=False,
            external_service_disclosed=True,
        )

        hybrid = LocalFirstSTTEngine(
            local_engine=mock_local,
            fallback_engine=mock_fallback,
            fallback_external_allowed=True,
        )

        mock_audio = MagicMock(spec=sr.AudioData)

        # 1. Local engine works -> fallback is NOT called
        res1 = hybrid.transcribe(mock_audio)
        self.assertEqual(res1.text, "local recognized command")
        self.assertTrue(res1.is_offline)
        mock_fallback.transcribe.assert_not_called()

        # 2. Local engine fails -> falls back to external service
        mock_local.transcribe.side_effect = RuntimeError("Vosk crashed")
        res2 = hybrid.transcribe(mock_audio)
        self.assertEqual(res2.text, "fallback command")
        self.assertFalse(res2.is_offline)
        self.assertTrue(res2.external_service_disclosed)

        # 3. Local engine fails and fallback is DISABLED -> does not call external service
        hybrid.fallback_external_allowed = False
        res3 = hybrid.transcribe(mock_audio)
        self.assertTrue(res3.is_empty)
        self.assertFalse(res3.external_service_disclosed)

    # --- 7. Recognition Timeouts and Listener Handling ---
    def test_listener_recognition_timeout_handling(self) -> None:
        listener = VoiceListener()
        # Mock capture raising WaitTimeoutError
        listener.capture.capture_audio = MagicMock(side_effect=sr.WaitTimeoutError("Timed out"))

        status_updates = []
        text = listener.listen_once(timeout=1, status_callback=lambda s: status_updates.append(s))

        self.assertEqual(text, "")
        self.assertIn("No speech detected", status_updates)

    # --- 8. Speaker, Interruptible Playback & Barge-in ---
    def test_speaker_interruptible_tts_and_barge_in(self) -> None:
        speaker = VoiceSpeaker()

        # Mock engine
        mock_engine = MagicMock()
        speaker.engine = mock_engine

        # Test queueing speech
        speaker.speak("Sentence one. Sentence two.")
        # Trigger barge-in
        speaker.barge_in()
        self.assertFalse(speaker.is_speaking)

        # Safe stop
        speaker.stop()
        self.assertTrue(speaker._stopped.is_set())

    # --- 9. Action-Bound Voice Confirmation Bridge ---
    def test_voice_confirmation_bridge_affirmative_approves(self) -> None:
        confirm_mgr = ConfirmationManager(default_timeout_s=30.0)
        bridge = VoiceConfirmationBridge(confirmation_manager=confirm_mgr)

        req = confirm_mgr.create_request(
            action="windows.shutdown",
            risk_level=3,
            summary="Shutdown system immediately",
        )

        # Exact affirmative speech
        is_approved, explanation = bridge.process_voice_response(req.token, "yes confirm")
        self.assertTrue(is_approved)
        self.assertIn("Approved", explanation)

        # Token is single-use; subsequent attempt must fail
        is_approved_again, _ = bridge.process_voice_response(req.token, "yes confirm")
        self.assertFalse(is_approved_again)

    def test_voice_confirmation_bridge_ambiguous_speech_strictly_rejected(self) -> None:
        confirm_mgr = ConfirmationManager(default_timeout_s=30.0)
        bridge = VoiceConfirmationBridge(confirmation_manager=confirm_mgr)

        # Ambiguous responses must NEVER approve an action
        ambiguous_samples = [
            "maybe",
            "what?",
            "who knows",
            "I guess so",
            "perhaps later",
            "why are you asking",
            "hello",
            "",
            "   ",
        ]

        for speech in ambiguous_samples:
            req = confirm_mgr.create_request(
                action="file.delete",
                risk_level=2,
                summary="Delete confidential file",
            )
            is_approved, explanation = bridge.process_voice_response(req.token, speech)
            self.assertFalse(is_approved, f"Speech '{speech}' should have been rejected!")
            self.assertTrue(
                "Unrecognized" in explanation or "cancelled" in explanation.lower() or "not recognized" in explanation.lower()
            )

    def test_voice_confirmation_bridge_negative_speech_cancels(self) -> None:
        confirm_mgr = ConfirmationManager(default_timeout_s=30.0)
        bridge = VoiceConfirmationBridge(confirmation_manager=confirm_mgr)

        req = confirm_mgr.create_request(
            action="windows.restart",
            risk_level=3,
            summary="Restart computer",
        )

        is_approved, explanation = bridge.process_voice_response(req.token, "cancel")
        self.assertFalse(is_approved)
        self.assertIn("cancelled", explanation.lower())

    # --- 10. Voice Pipeline Security Preservation ---
    def test_voice_does_not_bypass_policy_or_execution_engine(self) -> None:
        from security.kill_switch import get_kill_switch
        kill_switch = get_kill_switch()
        kill_switch.activate("Voice test kill switch")

        try:
            exec_engine = ExecutionEngine()
            req = TaskRequest(
                tool_name="system.shutdown",
                arguments={},
                user_confirmed=True,
            )
            res = exec_engine.execute(req)
            self.assertIn(res.status, ("CANCELLED", "DENIED"))
            self.assertIn("kill switch is active", res.message.lower())
        finally:
            kill_switch.deactivate()

    # --- 11. Language Support Tiers ---
    def test_language_support_tiers_and_status(self) -> None:
        self.assertEqual(VoiceLanguage.get_status("en"), LanguageStatus.PRODUCTION)
        self.assertEqual(VoiceLanguage.get_status("hi"), LanguageStatus.MEASURED_EXTERNAL)
        self.assertEqual(VoiceLanguage.get_status("or"), LanguageStatus.EXPERIMENTAL)

        self.assertFalse(VoiceLanguage.is_experimental("en"))
        self.assertFalse(VoiceLanguage.is_experimental("hi"))
        self.assertTrue(VoiceLanguage.is_experimental("or"))

    # --- 12. VoiceManager Integration Smoke Test (Legacy & Oliver modes) ---
    def test_voice_manager_smoke_legacy_and_oliver_modes(self) -> None:
        vm = VoiceManager(settings_path=self.settings_file)
        self.assertEqual(vm.current_state, VoiceState.READY)
        self.assertFalse(vm.is_microphone_active)

        # Mock dummy listener STT to prevent hardware dependency in test
        vm.listener.stt_engine = DummySTTEngine(transcript="what is the time")
        vm.listener.capture.capture_audio = MagicMock(return_value=MagicMock(spec=sr.AudioData))

        # Test listen_once state flow
        states_visited = []
        vm.add_state_listener(lambda st, d: states_visited.append(st))

        text = vm.listen_once()
        self.assertEqual(text, "what is the time")
        self.assertIn(VoiceState.LISTENING, states_visited)
        self.assertIn(VoiceState.READY, states_visited)

        # Smoke test with AshishAssistant in legacy mode
        assistant = AshishAssistant()
        reply_legacy = assistant.handle("what is the time")
        self.assertTrue(bool(reply_legacy))

        # Smoke test with AshishAssistant in oliver mode
        try:
            assistant.config.router_mode = "oliver"
            reply_oliver = assistant.handle("what is the time")
            self.assertTrue(bool(reply_oliver))
        finally:
            assistant.config.router_mode = self.orig_router_mode
            reload_config()


if __name__ == "__main__":
    unittest.main()
