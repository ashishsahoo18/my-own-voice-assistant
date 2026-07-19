"""Text-to-speech speaker for AYRA AI."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Optional

import pyttsx3


class VoiceSpeaker:
    """Speak text with configurable voice, speed, and volume."""

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: int = 170,
        volume: float = 1.0,
    ) -> None:
        self.voice_id = voice
        self.rate = max(80, min(300, rate))
        self.volume = max(0.0, min(1.0, volume))

        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self.engine: Optional[Any] = None

        try:
            self.engine = pyttsx3.init()
            self._configure_voice()
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Text-to-speech is unavailable; continuing without speech: %s",
                exc,
            )
            self.engine = None

    def _configure_voice(self) -> None:
        """Apply voice, rate, and volume to the TTS engine."""
        if self.engine is None:
            return

        voices = self.engine.getProperty("voices")
        preferred = self.voice_id

        if preferred:
            for voice in voices:
                if voice.id == preferred:
                    self.engine.setProperty("voice", voice.id)
                    break
        else:
            self._select_default_female_voice(voices)

        self.engine.setProperty("rate", self.rate)
        self.engine.setProperty("volume", self.volume)

    def _select_default_female_voice(self, voices: list[Any]) -> None:
        """Prefer a female English Windows voice when available."""
        if self.engine is None:
            return

        preferred_keywords = ["zira", "female", "susan", "hazel", "samantha"]

        for voice in voices:
            voice_name = str(getattr(voice, "name", "")).lower()
            voice_id = str(getattr(voice, "id", "")).lower()
            searchable = f"{voice_name} {voice_id}"

            if any(keyword in searchable for keyword in preferred_keywords):
                self.engine.setProperty("voice", voice.id)
                return

    def set_voice(self, voice_id: str) -> None:
        """Set voice by engine voice ID."""
        with self._lock:
            self.voice_id = voice_id or None
            self._configure_voice()

    def get_available_voices(self) -> list[dict[str, str]]:
        """Return available voices."""
        if self.engine is None:
            return []

        voices = []
        for voice in self.engine.getProperty("voices"):
            voices.append(
                {
                    "id": str(voice.id),
                    "name": str(voice.name),
                }
            )

        return voices

    def set_rate(self, rate: int) -> None:
        """Set speech speed."""
        with self._lock:
            self.rate = max(80, min(300, rate))
            if self.engine is not None:
                self.engine.setProperty("rate", self.rate)

    def set_volume(self, volume: float) -> None:
        """Set speech volume."""
        with self._lock:
            self.volume = max(0.0, min(1.0, volume))
            if self.engine is not None:
                self.engine.setProperty("volume", self.volume)

    def speak(self, text: str) -> None:
        """Speak text aloud."""
        clean_text = self._clean_text_for_speech(text)

        if not clean_text or self.engine is None:
            return

        with self._lock:
            if self._stopped.is_set():
                self._stopped.clear()

            try:
                self.engine.say(clean_text)
                self.engine.runAndWait()
            except RuntimeError as exc:
                logging.getLogger(__name__).warning("Speech runtime error: %s", exc)
            except Exception as exc:
                logging.getLogger(__name__).warning("Speech failed: %s", exc)

    def stop(self) -> None:
        """Stop current speech output."""
        self._stopped.set()

        with self._lock:
            if self.engine is not None:
                try:
                    self.engine.stop()
                except Exception as exc:
                    logging.getLogger(__name__).warning("Could not stop speech: %s", exc)

    def _clean_text_for_speech(self, text: str) -> str:
        """Remove markdown/code symbols so spoken output sounds natural."""
        clean_text = text.strip()

        clean_text = re.sub(r"```.*?```", "I have provided a code block.", clean_text, flags=re.DOTALL)
        clean_text = clean_text.replace("`", "")
        clean_text = clean_text.replace("#", "")
        clean_text = clean_text.replace("*", "")
        clean_text = clean_text.replace("_", "")
        clean_text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", clean_text)

        return clean_text.strip()