"""Offline-first Wake Word detection for OLIVER 2.0."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Optional

import speech_recognition as sr

from voice.audio_capture import AudioCapture
from voice.stt.base import SpeechToTextEngine
from voice.stt.local_first import LocalFirstSTTEngine


WakeCallback = Callable[[], None]


class WakeWordDetector:
    """Listen for a configured wake word in the background without persistent external audio transmission."""

    def __init__(
        self,
        wake_word: str = "hey oliver",
        logger: Optional[logging.Logger] = None,
        language: str = "en-US",
        stt_engine: Optional[SpeechToTextEngine] = None,
    ) -> None:
        self.wake_word = wake_word.lower().strip()
        self.language = language
        self.logger = logger or logging.getLogger(__name__)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[WakeCallback] = None
        self._last_triggered_at = 0.0
        self._cooldown_seconds = 2.0

        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.4

        self.capture = AudioCapture(logger=self.logger)
        self.stt_engine = stt_engine or LocalFirstSTTEngine(
            fallback_external_allowed=False,  # Wake word detection should NEVER send continuous audio to external cloud
            logger=self.logger,
        )

    @property
    def microphone(self) -> sr.Microphone:
        """Backward compatibility for microphone attribute."""
        return self.capture.get_microphone()

    def set_wake_word(self, wake_word: str) -> None:
        """Update wake word phrase."""
        clean_wake_word = wake_word.lower().strip()
        if clean_wake_word:
            self.wake_word = clean_wake_word

    def start(self, callback: WakeCallback) -> None:
        """Start listening for wake word in background."""
        if self._thread and self._thread.is_alive():
            return

        self._callback = callback
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="OliverWakeWordDetector",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop listening for wake word."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        """Background wake word detection loop."""
        self.logger.info("Wake word listener started (trigger: '%s')", self.wake_word)

        while not self._stop_event.is_set():
            try:
                heard_text = self._listen_for_short_phrase()
                if not heard_text:
                    continue

                if self._contains_wake_word(heard_text):
                    self._trigger_callback()
            except sr.WaitTimeoutError:
                continue
            except Exception as exc:
                self.logger.debug("Wake word loop non-fatal event: %s", exc)
                time.sleep(0.3)

        self.logger.info("Wake word listener stopped")

    def _listen_for_short_phrase(self) -> str:
        """Capture a short audio phrase and transcribe it locally offline."""
        try:
            audio = self.capture.capture_audio(
                recognizer=self.recognizer,
                timeout=1.0,
                phrase_time_limit=2.5,
                ambient_duration=0.0,
            )
            result = self.stt_engine.transcribe(audio, language=self.language)
            return result.text.lower().strip()
        except sr.WaitTimeoutError:
            return ""
        except Exception:
            return ""

    def _contains_wake_word(self, text: str) -> bool:
        """Check if transcribed phrase contains target wake word or alias."""
        if not self.wake_word or not text:
            return False

        # Match exact word or tokens
        words = text.split()
        wake_words = self.wake_word.split()

        if self.wake_word in text:
            return True

        # Check subphrase match
        if len(wake_words) > 1 and all(w in text for w in wake_words):
            return True

        return False

    def _trigger_callback(self) -> None:
        """Trigger callback with debounce cooldown."""
        now = time.monotonic()
        if now - self._last_triggered_at < self._cooldown_seconds:
            return

        self._last_triggered_at = now
        self.logger.info("Wake word detected!")

        if self._callback is not None:
            try:
                self._callback()
            except Exception as exc:
                self.logger.warning("Error in wake word callback: %s", exc)