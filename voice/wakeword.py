"""Wake word detection for AYRA AI."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Optional

import speech_recognition as sr


WakeCallback = Callable[[], None]


class WakeWordDetector:
    """Listen for a configured wake word in the background."""

    def __init__(
        self,
        wake_word: str = "hey ayra",
        logger: Optional[logging.Logger] = None,
        language: str = "en-US",
    ) -> None:
        self.wake_word = wake_word.lower().strip()
        self.language = language
        self.logger = logger

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[WakeCallback] = None
        self._last_triggered_at = 0.0
        self._cooldown_seconds = 3.0

        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.5

        self.microphone = sr.Microphone()

    def set_wake_word(self, wake_word: str) -> None:
        """Update wake word text."""
        clean_wake_word = wake_word.lower().strip()
        if clean_wake_word:
            self.wake_word = clean_wake_word

    def start(self, callback: WakeCallback) -> None:
        """Start listening for the wake word."""
        if self._thread and self._thread.is_alive():
            return

        self._callback = callback
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="AyraWakeWordDetector",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop listening for the wake word."""
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self) -> None:
        """Background wake-word loop."""
        self._log_info("Wake word listener started")

        while not self._stop_event.is_set():
            try:
                heard_text = self._listen_for_short_phrase()

                if not heard_text:
                    continue

                if self._contains_wake_word(heard_text):
                    self._trigger_callback()
            except sr.UnknownValueError:
                continue
            except sr.WaitTimeoutError:
                continue
            except Exception as exc:
                self._log_error("Wake word detection error: %s", exc)
                time.sleep(0.5)

        self._log_info("Wake word listener stopped")

    def _listen_for_short_phrase(self) -> str:
        """Listen for a short audio phrase and return recognized text."""
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
            audio = self.recognizer.listen(
                source,
                timeout=1,
                phrase_time_limit=2,
            )

        text = self.recognizer.recognize_google(audio, language=self.language)
        return text.lower().strip()

    def _contains_wake_word(self, text: str) -> bool:
        """Return True if recognized text contains the wake word."""
        return bool(self.wake_word and self.wake_word in text)

    def _trigger_callback(self) -> None:
        """Trigger wake callback with cooldown protection."""
        now = time.monotonic()

        if now - self._last_triggered_at < self._cooldown_seconds:
            return

        self._last_triggered_at = now
        self._log_info("Wake word detected")

        if self._callback is not None:
            self._callback()

    def _log_info(self, message: str) -> None:
        """Log info when logger exists."""
        if self.logger is not None:
            self.logger.info(message)

    def _log_error(self, message: str, exc: Exception) -> None:
        """Log error when logger exists."""
        if self.logger is not None:
            self.logger.error(message, exc)