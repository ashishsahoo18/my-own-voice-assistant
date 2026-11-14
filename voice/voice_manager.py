"""Central voice coordinator for OLIVER 2.0 with modular pipeline and safe barge-in."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from voice.confirmation_bridge import VoiceConfirmationBridge
from voice.language import VoiceLanguage
from voice.listener import VoiceListener
from voice.speaker import VoiceSpeaker
from voice.states import VoiceState, VoiceStateMachine
from voice.stt.base import TranscriptionResult
from voice.wakeword import WakeWordDetector


StatusCallback = Callable[[str], None]
WakeCallback = Callable[[], None]


class VoiceManager:
    """Central voice pipeline orchestrator coordinating capture, VAD, STT, TTS, state, and confirmations."""

    def __init__(
        self,
        settings_path: Optional[str | Path] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.settings_path = Path(settings_path or self.base_dir / "config" / "voice_settings.json")
        self.logger = logger or self._create_logger()
        self._lock = threading.RLock()
        self._is_listening = False

        self.state_machine = VoiceStateMachine(initial_state=VoiceState.READY, logger=self.logger)
        self.settings = self._load_settings()
        self.last_transcription_result: Optional[TranscriptionResult] = None

        # Modular components
        fallback_allowed = bool(self.settings.get("fallback_external_allowed", True))
        self.listener = VoiceListener(
            logger=self.logger,
            language=self._recognition_language,
            fallback_external_allowed=fallback_allowed,
        )

        self.speaker = VoiceSpeaker(
            voice=self.settings.get("voice_id"),
            rate=int(self.settings.get("speech_rate", 170)),
            volume=float(self.settings.get("volume", 1.0)),
            on_speaking_changed=self._on_speaking_changed,
            logger=self.logger,
        )

        self.wake_detector = WakeWordDetector(
            wake_word=str(self.settings.get("wake_word", "hey oliver")),
            wake_phrases=self.settings.get("wake_phrases"),
            logger=self.logger,
            language=self._recognition_language,
        )

        self.confirmation_bridge = VoiceConfirmationBridge(logger=self.logger)

    @property
    def current_state(self) -> VoiceState:
        """Current pipeline state."""
        return self.state_machine.current_state

    @property
    def is_microphone_active(self) -> bool:
        """True if microphone hardware is currently open and active."""
        return self.listener.capture.is_active

    @property
    def stt_engine_name(self) -> str:
        """Return the active primary STT engine name."""
        if hasattr(self.listener, "stt_engine"):
            engine = self.listener.stt_engine
            if hasattr(engine, "local_engine"):
                return "Vosk"
            if hasattr(engine, "name"):
                return "Vosk" if "vosk" in str(engine.name).lower() else str(engine.name).capitalize()
        return "Vosk"

    @property
    def is_stt_available(self) -> bool:
        """Return True if the underlying STT engine is initialized and available."""
        if not self.settings.get("voice_enabled", True):
            return False
        if hasattr(self.listener, "stt_engine") and hasattr(self.listener.stt_engine, "is_available"):
            try:
                return bool(self.listener.stt_engine.is_available())
            except Exception:
                return False
        return True

    @property
    def _recognition_language(self) -> str:
        """Return speech-recognition language code."""
        language = str(self.settings.get("language", "en"))
        return VoiceLanguage.to_recognition_language(language)

    def _on_speaking_changed(self, is_speaking: bool) -> None:
        """Update VoiceStateMachine when speaker starts or finishes output."""
        if is_speaking:
            self.state_machine.transition_to(VoiceState.SPEAKING)
        else:
            if self.state_machine.current_state == VoiceState.SPEAKING:
                self.state_machine.transition_to(VoiceState.READY)

    def add_state_listener(self, callback: Callable[[VoiceState, Optional[str]], None]) -> None:
        """Register a callback for voice state transitions."""
        self.state_machine.add_listener(callback)

    def remove_state_listener(self, callback: Callable[[VoiceState, Optional[str]], None]) -> None:
        """Unregister a state callback."""
        self.state_machine.remove_listener(callback)

    def set_state(self, state: VoiceState | str, detail: Optional[str] = None) -> VoiceState:
        """Manually trigger a state machine transition."""
        if isinstance(state, str):
            state = VoiceState(state.upper())
        return self.state_machine.transition_to(state, detail)

    def barge_in(self) -> None:
        """Safe barge-in: immediately abort active speech synthesis and release audio output."""
        self.logger.info("Barge-in requested on VoiceManager")
        self.speaker.barge_in()
        if self.state_machine.current_state == VoiceState.SPEAKING:
            self.state_machine.transition_to(VoiceState.READY, detail="barge_in")

    def listen_once_result(
        self,
        status_callback: Optional[StatusCallback] = None,
        timeout: int = 10,
        phrase_time_limit: Optional[int] = 15,
        silence_timeout: float = 1.0,
    ) -> TranscriptionResult:
        """Capture user speech once and return structured TranscriptionResult metadata."""
        if not self.settings.get("voice_enabled", True):
            res = TranscriptionResult(text="", confidence=0.0, engine="disabled", confidence_available=True)
            self.last_transcription_result = res
            return res

        with self._lock:
            if self._is_listening:
                self.logger.warning("Voice listening already active; ignoring duplicate session request.")
                res = TranscriptionResult(text="", confidence=0.0, engine="busy", confidence_available=True)
                self.last_transcription_result = res
                return res
            self._is_listening = True

        # Safe barge-in: stop any active speech output before opening the microphone
        self.barge_in()

        # Stage 2E Condition 1: Pause background wake-word capture and verify hardware release
        wake_was_paused = False
        if hasattr(self, "wake_detector") and self.wake_detector is not None:
            try:
                paused_ok = self.wake_detector.pause(timeout=2.0)
                if not paused_ok:
                    self.logger.warning(
                        "Could not confirm wake word microphone release within timeout; failing safely to prevent stream conflict"
                    )
                    with self._lock:
                        self._is_listening = False
                    self.wake_detector.resume()
                    res = TranscriptionResult(
                        text="",
                        confidence=0.0,
                        engine="mic_busy",
                        details={"error": "Microphone release timeout"},
                        confidence_available=False,
                    )
                    self.last_transcription_result = res
                    return res
                wake_was_paused = True
            except Exception as exc:
                self.logger.error("Error pausing wake word detector: %s", exc)

        self.state_machine.transition_to(VoiceState.LISTENING)
        self.logger.info("Voice listening started (timeout=%ss, phrase_limit=%ss)", timeout, phrase_time_limit)

        def wrapped_status_cb(st: str) -> None:
            if st.lower() == "listening":
                self.state_machine.transition_to(VoiceState.LISTENING)
            elif st.lower() == "processing":
                self.state_machine.transition_to(VoiceState.PROCESSING)
            if status_callback:
                status_callback(st)

        try:
            result = self.listener.listen_once_result(
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
                silence_timeout=silence_timeout,
                status_callback=wrapped_status_cb,
            )
            self.last_transcription_result = result
            self.logger.info(
                "Voice listening completed (recognized: '%s', confidence=%s, available=%s)",
                result.text,
                result.confidence,
                result.confidence_available,
            )
            self.state_machine.transition_to(VoiceState.READY)
            return result
        except Exception as exc:
            self.logger.error("Voice recognition error: %s", exc)
            self.state_machine.transition_to(VoiceState.ERROR, detail=str(exc))
            res = TranscriptionResult(
                text="",
                confidence=0.0,
                engine="error",
                details={"error": str(exc)},
                confidence_available=True,
            )
            self.last_transcription_result = res
            return res
        finally:
            if wake_was_paused:
                try:
                    self.wake_detector.resume()
                except Exception as exc:
                    self.logger.error("Error resuming wake word detector: %s", exc)
            with self._lock:
                self._is_listening = False

    def listen_once(
        self,
        status_callback: Optional[StatusCallback] = None,
        timeout: int = 10,
        phrase_time_limit: Optional[int] = 15,
        silence_timeout: float = 1.0,
    ) -> str:
        """Capture user speech once, performing safe barge-in and state transitions."""
        result = self.listen_once_result(
            status_callback=status_callback,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            silence_timeout=silence_timeout,
        )
        return result.text.strip()

    def speak(self, text: str, wait: bool = False) -> None:
        """Speak text aloud using the configured TTS engine."""
        clean_text = (text or "").strip()
        if not clean_text or not self.settings.get("voice_enabled", True) or not self.settings.get("auto_speaking", True):
            return

        try:
            self.speaker.speak(clean_text, wait=wait)
        except Exception as exc:
            self.logger.error("Speech error: %s", exc)
            self.state_machine.transition_to(VoiceState.ERROR, detail=str(exc))

    def confirm_action_by_voice(
        self,
        token: str,
        prompt_text: Optional[str] = None,
        timeout: int = 6,
    ) -> tuple[bool, str]:
        """Ask for voice confirmation bound to a specific security token."""
        if prompt_text:
            self.speak(prompt_text, wait=True)

        spoken_text = self.listen_once(timeout=timeout, phrase_time_limit=4)
        return self.confirmation_bridge.process_voice_response(token, spoken_text)

    def start_wake_word_listener(self, callback: WakeCallback) -> None:
        """Start continuous offline wake-word detection."""
        if not self.settings.get("voice_enabled", True) or not self.settings.get("wake_word_enabled", True):
            return

        def safe_wake_callback() -> None:
            self.barge_in()
            callback()

        self.wake_detector.start(safe_wake_callback)

    def stop_wake_word_listener(self) -> None:
        """Stop wake-word detection."""
        self.wake_detector.stop()

    def pause_wake_word(self, timeout: float = 2.0) -> bool:
        """Pause background wake-word detection (e.g. for PTT or external audio)."""
        if hasattr(self, "wake_detector") and self.wake_detector is not None:
            return self.wake_detector.pause(timeout=timeout)
        return True

    def resume_wake_word(self, force: bool = False) -> None:
        """Resume background wake-word detection."""
        if hasattr(self, "wake_detector") and self.wake_detector is not None:
            self.wake_detector.resume(force=force)

    def stop_speaking(self) -> None:
        """Stop current speech output."""
        self.barge_in()

    def get_available_voices(self) -> list[dict[str, str]]:
        """Return installed TTS voices."""
        return self.speaker.get_available_voices()

    def set_language(self, language: str) -> None:
        """Set recognition language."""
        self.save_settings(language=language)

    @property
    def wake_phrases(self) -> list[str]:
        """Return currently configured wake phrases (Stage 2D)."""
        return list(self.wake_detector.wake_phrases)

    def set_wake_phrases(self, wake_phrases: Any) -> None:
        """Set dual or multiple wake phrases (Stage 2D)."""
        self.wake_detector.set_wake_phrases(wake_phrases)
        phrases = list(self.wake_detector.wake_phrases)
        self.save_settings(wake_phrases=phrases, wake_word=phrases[0])

    def set_wake_word(self, wake_word: str) -> None:
        """Set primary wake word."""
        clean_wake_word = wake_word.strip().lower()
        if clean_wake_word:
            self.wake_detector.set_wake_word(clean_wake_word)
            phrases = list(self.wake_detector.wake_phrases)
            self.save_settings(wake_word=clean_wake_word, wake_phrases=phrases)

    def enable_voice(self, enabled: bool) -> None:
        """Enable or disable all voice features."""
        self.save_settings(voice_enabled=enabled)

    def _create_logger(self) -> logging.Logger:
        """Create or reuse the voice logger."""
        log_path = self.base_dir / "logs" / "voice.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("oliver.voice")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if not logger.handlers:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)

        return logger

    def _load_settings(self) -> dict[str, Any]:
        """Load voice settings from JSON."""
        defaults = self._default_settings()
        if not self.settings_path.exists():
            self._write_settings(defaults)
            return defaults

        try:
            with self.settings_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, dict):
                defaults.update(data)
            return defaults
        except Exception as exc:
            self.logger.error("Failed to load voice settings: %s", exc)
            return defaults

    def save_settings(self, **updates: Any) -> None:
        """Persist voice settings and apply them immediately."""
        with self._lock:
            self.settings.update(updates)
            self._write_settings(self.settings)
            self._apply_runtime_settings()

    def _write_settings(self, settings: dict[str, Any]) -> None:
        """Write voice settings JSON."""
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings_path.open("w", encoding="utf-8") as file:
            json.dump(settings, file, indent=2)

    def _default_settings(self) -> dict[str, Any]:
        """Return default voice settings."""
        return {
            "voice_enabled": True,
            "auto_speaking": True,
            "auto_send_voice": False,
            "voice_id": None,
            "speech_rate": 170,
            "volume": 1.0,
            "language": "en",
            "wake_word": "hey oliver",
            "wake_phrases": ["hey oliver", "hello oliver"],
            "wake_word_enabled": True,
            "push_to_talk_enabled": True,
            "fallback_external_allowed": True,
        }

    def _apply_runtime_settings(self) -> None:
        """Apply saved settings to active voice components."""
        self.listener.language = self._recognition_language
        self.listener.stt_engine.fallback_external_allowed = bool(self.settings.get("fallback_external_allowed", True))
        self.speaker.set_rate(int(self.settings.get("speech_rate", 170)))
        self.speaker.set_volume(float(self.settings.get("volume", 1.0)))
        self.speaker.set_voice(str(self.settings.get("voice_id") or ""))
        raw_phrases = self.settings.get("wake_phrases")
        if raw_phrases:
            self.wake_detector.set_wake_phrases(raw_phrases)
        else:
            primary = str(self.settings.get("wake_word", "hey oliver"))
            self.wake_detector.set_wake_phrases([primary, "hello oliver"])
        self.wake_detector.language = self._recognition_language
