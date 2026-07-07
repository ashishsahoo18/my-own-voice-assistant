from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

from voice.language import VoiceLanguage
from voice.listener import VoiceListener
from voice.speaker import VoiceSpeaker
from voice.wakeword import WakeWordDetector


class VoiceManager:
    """Central voice controller for listening, speaking, and wake-word handling."""

    def __init__(self, settings_path: Optional[str] = None, logger: Optional[logging.Logger] = None) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.settings_path = Path(settings_path or self.base_dir / "config" / "voice_settings.json")
        self.logger = logger or self._create_logger()
        self.settings = self._load_settings()
        self.listener = VoiceListener(logger=self.logger, language=self._recognition_language)
        self.speaker = VoiceSpeaker(
            voice=self.settings.get("voice_id"),
            rate=int(self.settings.get("speech_rate", 170)),
            volume=float(self.settings.get("volume", 1.0)),
        )
        self.wake_detector = WakeWordDetector(wake_word=self.settings.get("wake_word", "hey ayra"), logger=self.logger)
        self._lock = threading.Lock()

    @property
    def _recognition_language(self) -> str:
        return VoiceLanguage.to_recognition_language(self.settings.get("language", "en"))

    def _create_logger(self) -> logging.Logger:
        log_path = self.base_dir / "logs" / "voice.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("ayra.voice")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger

    def _load_settings(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return self._default_settings()
        try:
            with self.settings_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            settings = self._default_settings()
            settings.update(data)
            return settings
        except Exception as exc:
            self.logger.error("Failed to load voice settings: %s", exc)
            return self._default_settings()

    def save_settings(self, **updates: Any) -> None:
        with self._lock:
            self.settings.update(updates)
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with self.settings_path.open("w", encoding="utf-8") as fh:
                json.dump(self.settings, fh, indent=2)
            self._apply_runtime_settings()

    def _default_settings(self) -> dict[str, Any]:
        return {
            "voice_enabled": True,
            "auto_speaking": True,
            "voice_id": None,
            "speech_rate": 170,
            "volume": 1.0,
            "language": "en",
            "wake_word": "hey ayra",
        }

    def _apply_runtime_settings(self) -> None:
        self.listener.language = self._recognition_language
        self.speaker.set_rate(int(self.settings.get("speech_rate", 170)))
        self.speaker.set_volume(float(self.settings.get("volume", 1.0)))
        self.speaker.set_voice(self.settings.get("voice_id") or "")
        self.wake_detector.set_wake_word(self.settings.get("wake_word", "hey ayra"))

    def listen_once(self, status_callback=None) -> str:
        if not self.settings.get("voice_enabled", True):
            return ""
        self.logger.info("Start listening")
        try:
            text = self.listener.listen_once(status_callback=status_callback)
            self.logger.info("End listening")
            return text
        except Exception as exc:  # pragma: no cover - defensive guard
            self.logger.error("Recognition errors: %s", exc)
            return ""

    def speak(self, text: str) -> None:
        if not self.settings.get("voice_enabled", True):
            return
        if not self.settings.get("auto_speaking", True):
            return
        self.logger.info("Speech completed")
        self.speaker.speak(text)

    def start_wake_word_listener(self, callback) -> None:
        if not self.settings.get("voice_enabled", True):
            return
        self.wake_detector.start(callback)

    def stop_wake_word_listener(self) -> None:
        self.wake_detector.stop()

    def stop_speaking(self) -> None:
        self.speaker.stop()

    def get_available_voices(self) -> list[dict[str, str]]:
        return self.speaker.get_available_voices()
