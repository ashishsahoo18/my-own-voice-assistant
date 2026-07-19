"""Voice manager for AYRA AI."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from voice.language import VoiceLanguage
from voice.listener import VoiceListener
from voice.speaker import VoiceSpeaker
from voice.wakeword import WakeWordDetector


StatusCallback = Callable[[str], None]
WakeCallback = Callable[[], None]


class VoiceManager:
    """Central voice controller for listening, speaking, and wake-word handling."""

    def __init__(
        self,
        settings_path: Optional[str | Path] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.settings_path = Path(settings_path or self.base_dir / "config" / "voice_settings.json")
        self.logger = logger or self._create_logger()
        self._lock = threading.RLock()

        self.settings = self._load_settings()
        self.listener = VoiceListener(
            logger=self.logger,
            language=self._recognition_language,
        )
        self.speaker = VoiceSpeaker(
            voice=self.settings.get("voice_id"),
            rate=int(self.settings.get("speech_rate", 170)),
            volume=float(self.settings.get("volume", 1.0)),
        )
        self.wake_detector = WakeWordDetector(
            wake_word=str(self.settings.get("wake_word", "hey ayra")),
            logger=self.logger,
        )

    @property
    def _recognition_language(self) -> str:
        """Return the speech-recognition language code."""
        language = str(self.settings.get("language", "en"))
        return VoiceLanguage.to_recognition_language(language)

    def _create_logger(self) -> logging.Logger:
        """Create or reuse the voice logger."""
        log_path = self.base_dir / "logs" / "voice.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("ayra.voice")
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

            if not isinstance(data, dict):
                return defaults

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
            "wake_word": "hey ayra",
            "wake_word_enabled": True,
            "push_to_talk_enabled": True,
        }

    def _apply_runtime_settings(self) -> None:
        """Apply saved settings to active voice components."""
        self.listener.language = self._recognition_language
        self.speaker.set_rate(int(self.settings.get("speech_rate", 170)))
        self.speaker.set_volume(float(self.settings.get("volume", 1.0)))
        self.speaker.set_voice(str(self.settings.get("voice_id") or ""))
        self.wake_detector.set_wake_word(str(self.settings.get("wake_word", "hey ayra")))

    def listen_once(self, status_callback: Optional[StatusCallback] = None) -> str:
        """Listen once and return recognized text."""
        if not self.settings.get("voice_enabled", True):
            return ""

        self.logger.info("Voice listening started")

        try:
            text = self.listener.listen_once(status_callback=status_callback)
            self.logger.info("Voice listening completed")
            return text
        except Exception as exc:
            self.logger.error("Recognition error: %s", exc)
            return ""

    def speak(self, text: str) -> None:
        """Speak text using the configured TTS engine."""
        clean_text = text.strip()

        if not clean_text:
            return

        if not self.settings.get("voice_enabled", True):
            return

        if not self.settings.get("auto_speaking", True):
            return

        try:
            self.speaker.speak(clean_text)
            self.logger.info("Speech completed")
        except Exception as exc:
            self.logger.error("Speech error: %s", exc)

    def start_wake_word_listener(self, callback: WakeCallback) -> None:
        """Start continuous wake-word detection."""
        if not self.settings.get("voice_enabled", True):
            return

        if not self.settings.get("wake_word_enabled", True):
            return

        self.wake_detector.start(callback)

    def stop_wake_word_listener(self) -> None:
        """Stop wake-word detection."""
        self.wake_detector.stop()

    def stop_speaking(self) -> None:
        """Stop current speech output."""
        self.speaker.stop()

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