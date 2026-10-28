"""Speech recognition listener for OLIVER 2.0 with modular capture and local-first STT."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional

import speech_recognition as sr

from voice.audio_capture import AudioCapture, MicrophoneError
from voice.stt.base import SpeechToTextEngine, TranscriptionResult
from voice.stt.local_first import LocalFirstSTTEngine
from voice.vad import VoiceActivityDetector


StatusCallback = Callable[[str], None]


class VoiceListener:
    """Capture spoken input using modular audio capture, VAD, and local-first STT."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        language: str = "en-US",
        stt_engine: Optional[SpeechToTextEngine] = None,
        fallback_external_allowed: bool = True,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.language = language

        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.recognizer.non_speaking_duration = 0.4

        self.capture = AudioCapture(logger=self.logger)
        self.vad = VoiceActivityDetector()
        self.stt_engine = stt_engine or LocalFirstSTTEngine(
            fallback_external_allowed=fallback_external_allowed,
            logger=self.logger,
        )

        self.last_result: Optional[TranscriptionResult] = None

    @property
    def microphone(self) -> sr.Microphone:
        """Backward-compatible access to underlying microphone instance."""
        return self.capture.get_microphone()

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
            self._notify(status_callback, "Listening")
            audio = self.capture.capture_audio(
                recognizer=self.recognizer,
                timeout=float(timeout),
                phrase_time_limit=float(phrase_time_limit) if phrase_time_limit else None,
            )
            self._notify(status_callback, "Processing")
        except sr.WaitTimeoutError:
            self._log_warning("Voice listening timed out; no speech detected")
            self._notify(status_callback, "No speech detected")
            return ""
        except (MicrophoneError, OSError) as exc:
            self._log_error("Microphone hardware error: %s", exc)
            self._notify(status_callback, "Microphone error")
            raise RuntimeError(f"Microphone error: {exc}") from exc
        except Exception as exc:
            self._log_error("Listening failed: %s", exc)
            self._notify(status_callback, "Error")
            raise RuntimeError(f"Unable to access microphone: {exc}") from exc

        return self._recognize_audio(audio)

    def _recognize_audio(self, audio: sr.AudioData) -> str:
        """Recognize captured audio data using configured STT engine."""
        try:
            result = self.stt_engine.transcribe(audio, language=self.language)
            self.last_result = result
            return result.text.strip()
        except Exception as exc:
            self._log_error("Speech recognition failed: %s", exc)
            raise RuntimeError(f"Speech recognition unavailable: {exc}") from exc

    def _notify(self, callback: Optional[StatusCallback], status: str) -> None:
        """Send status updates to the UI."""
        if callback is not None:
            try:
                callback(status)
            except Exception as exc:
                self._log_warning(f"Error in status callback: {exc}")

    def _log_warning(self, message: str) -> None:
        """Log a warning."""
        if self.logger is not None:
            self.logger.warning(message)

    def _log_error(self, message: str, exc: Exception) -> None:
        """Log an error."""
        if self.logger is not None:
            self.logger.error(message, exc)