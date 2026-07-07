import logging
from typing import Callable, Optional

import speech_recognition as sr


class VoiceListener:
    """Capture spoken input using the system microphone."""

    def __init__(self, logger: Optional[logging.Logger] = None, language: str = "en-US") -> None:
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.microphone = sr.Microphone()
        self.logger = logger
        self.language = language

    def listen_once(
        self,
        timeout: int = 8,
        phrase_time_limit: Optional[int] = 8,
        silence_timeout: int = 2,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Capture speech once and return the recognized text."""
        try:
            with self.microphone as source:
                if status_callback is not None:
                    status_callback("Listening...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                if status_callback is not None:
                    status_callback("Processing...")
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
        except sr.WaitTimeoutError:
            if self.logger is not None:
                self.logger.warning("Voice listening timed out")
            return ""
        except OSError as exc:
            if self.logger is not None:
                self.logger.error("Microphone error: %s", exc)
            raise RuntimeError(f"Microphone error: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive guard
            if self.logger is not None:
                self.logger.error("Listening failed: %s", exc)
            raise RuntimeError(f"Unable to access microphone: {exc}") from exc

        try:
            text = self.recognizer.recognize_google(audio, language=self.language)
            return text.strip()
        except sr.UnknownValueError:
            if self.logger is not None:
                self.logger.warning("Speech was not recognized")
            return ""
        except sr.RequestError as exc:
            if self.logger is not None:
                self.logger.error("Speech recognition request failed: %s", exc)
            raise RuntimeError(f"Speech recognition unavailable: {exc}") from exc
