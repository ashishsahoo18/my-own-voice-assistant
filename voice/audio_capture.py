"""Microphone audio capture and lifecycle management for OLIVER 2.0."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import speech_recognition as sr


class MicrophoneError(RuntimeError):
    """Raised when microphone hardware or driver is unavailable or fails."""


class AudioCapture:
    """Manages microphone hardware lifecycle, ambient noise calibration, and raw audio streaming."""

    def __init__(
        self,
        device_index: Optional[int] = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.logger = logger or logging.getLogger(__name__)

        self._lock = threading.RLock()
        self._is_active = False
        self._microphone: Optional[sr.Microphone] = None
        self._active_source: Optional[Any] = None

    @property
    def is_active(self) -> bool:
        """Return True if microphone is actively capturing audio."""
        with self._lock:
            return self._is_active

    def get_microphone(self) -> sr.Microphone:
        """Create or return standard SpeechRecognition Microphone instance."""
        with self._lock:
            if self._microphone is None:
                try:
                    self._microphone = sr.Microphone(
                        device_index=self.device_index,
                        sample_rate=self.sample_rate,
                        chunk_size=self.chunk_size,
                    )
                except Exception as exc:
                    self.logger.error("Failed to initialize microphone hardware: %s", exc)
                    raise MicrophoneError(f"Microphone initialization failed: {exc}") from exc
            return self._microphone

    def open_stream(self) -> Any:
        """Explicitly open microphone audio stream."""
        with self._lock:
            if self._is_active:
                return self._active_source

            try:
                mic = self.get_microphone()
                self._active_source = mic.__enter__()
                self._is_active = True
                self.logger.info("Microphone hardware stream opened (device_index=%s)", self.device_index)
                return self._active_source
            except OSError as exc:
                self._is_active = False
                self._active_source = None
                self.logger.error("OS/Hardware microphone error: %s", exc)
                raise MicrophoneError(f"Hardware microphone unavailable: {exc}") from exc
            except Exception as exc:
                self._is_active = False
                self._active_source = None
                self.logger.error("Unexpected error opening microphone stream: %s", exc)
                raise MicrophoneError(f"Could not open microphone stream: {exc}") from exc

    def close_stream(self) -> None:
        """Explicitly close microphone stream and release hardware."""
        with self._lock:
            if not self._is_active or self._active_source is None:
                self._is_active = False
                self._active_source = None
                return

            try:
                if self._microphone is not None:
                    self._microphone.__exit__(None, None, None)
            except Exception as exc:
                self.logger.warning("Error closing microphone stream: %s", exc)
            finally:
                self._is_active = False
                self._active_source = None
                self.logger.info("Microphone hardware stream closed")

    def capture_audio(
        self,
        recognizer: sr.Recognizer,
        timeout: Optional[float] = 8.0,
        phrase_time_limit: Optional[float] = 10.0,
        ambient_duration: float = 0.4,
    ) -> sr.AudioData:
        """Safely capture speech audio with explicit hardware management and error isolation.
        
        Raw audio is held only in memory as sr.AudioData and never written to disk by default.
        """
        with self._lock:
            try:
                mic = self.get_microphone()
                with mic as source:
                    self._is_active = True
                    if ambient_duration > 0:
                        recognizer.adjust_for_ambient_noise(source, duration=ambient_duration)

                    audio = recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_time_limit,
                    )
                    return audio
            except sr.WaitTimeoutError:
                self.logger.info("Listening timed out with no speech detected")
                raise
            except OSError as exc:
                self.logger.error("Microphone hardware error during capture: %s", exc)
                raise MicrophoneError(f"Microphone device error: {exc}") from exc
            except Exception as exc:
                self.logger.error("Speech capture failed: %s", exc)
                raise MicrophoneError(f"Microphone capture failure: {exc}") from exc
            finally:
                self._is_active = False
