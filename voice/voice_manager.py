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

        self.state_machine = VoiceStateMachine(initial_state=VoiceState.READY, logger=self.logger)
        self.settings = self._load_settings()

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

    def listen_once(
        self,
        status_callback: Optional[StatusCallback] = None,
        timeout: int = 8,
        phrase_time_limit: Optional[int] = 8,
        silence_timeout: float = 0.8,
    ) -> str:
        """Capture user speech once, performing safe barge-in and state transitions."""
        if not self.settings.get("voice_enabled", True):
            return ""

        # Safe barge-in: stop any active speech output before opening the microphone
        self.barge_in()

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
            text = self.listener.listen_once(
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
                silence_timeout=silence_timeout,
                status_callback=wrapped_status_cb,
            )
            self.logger.info("Voice listening completed (recognized: '%s')", text)
            self.state_machine.transition_to(VoiceState.READY)
            return text
        except Exception as exc:
            self.logger.error("Voice recognition error: %s", exc)
            self.state_machine.transition_to(VoiceState.ERROR, detail=str(exc))
            return ""

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

    def stop_speaking(self) -> None:
        """Stop current speech output."""
        self.barge_in()

    def get_available_voices(self) -> list[dict[str, str]]:
        """Return installed TTS voices."""
        return self.speaker.get_available_voices()

    def set_language(self, language: str) -> None:
        """Set recognition language."""
        self.save_settings(language=language)

    def set_wake_word(self, wake_word: str) -> None:
        """Set wake word."""
        clean_wake_word = wake_word.strip().lower()
        if clean_wake_word:
            self.save_settings(wake_word=clean_wake_word)

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
        self.wake_detector.set_wake_word(str(self.settings.get("wake_word", "hey oliver")))
        self.wake_detector.language = self._recognition_language