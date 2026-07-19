"""Speech recognition listener for AYRA AI."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional

import speech_recognition as sr


StatusCallback = Callable[[str], None]


class VoiceListener:
    """Capture spoken input using the system microphone."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        language: str = "en-US",
    ) -> None:
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.recognizer.non_speaking_duration = 0.4

        self.microphone = sr.Microphone()
        self.logger = logger
        self.language = language

    def listen_once(
        self,
        timeout: int = 8,
        phrase_time_limit: Optional[int] = 8,
        silence_timeout: float = 0.8,
        status_callback: Optional[StatusCallback] = None,
    ) -> str:
        """Capture speech once and return recognized text."""
        self.recognizer.pause_threshold = silence_timeout

        try:
            with self.microphone as source:
                self._notify(status_callback, "Listening")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )

                self._notify(status_callback, "Processing")
        except sr.WaitTimeoutError:
            self._log_warning("Voice listening timed out")
            self._notify(status_callback, "No speech detected")
            return ""
        except OSError as exc:
            self._log_error("Microphone error: %s", exc)
            raise RuntimeError(f"Microphone error: {exc}") from exc
        except Exception as exc:
            self._log_error("Listening failed: %s", exc)
            raise RuntimeError(f"Unable to access microphone: {exc}") from exc

        return self._recognize_audio(audio)

    def _recognize_audio(self, audio: sr.AudioData) -> str:
        """Recognize audio using Google speech recognition."""
        try:
            text = self.recognizer.recognize_google(audio, language=self.language)
            return text.strip()
        except sr.UnknownValueError:
            self._log_warning("Speech was not recognized")
            return ""
        except sr.RequestError as exc:
            self._log_error("Speech recognition request failed: %s", exc)
            raise RuntimeError(f"Speech recognition unavailable: {exc}") from exc

    def _notify(self, callback: Optional[StatusCallback], status: str) -> None:
        """Send status updates to the UI."""
        if callback is not None:
            callback(status)

    def _log_warning(self, message: str) -> None:
        """Log a warning when a logger exists."""
        if self.logger is not None:
            self.logger.warning(message)

    def _log_error(self, message: str, exc: Exception) -> None:
        """Log an error when a logger exists."""
        if self.logger is not None:
            self.logger.error(message, exc)