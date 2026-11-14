"""Offline-first Wake Word detection for OLIVER 3.0 (Stage 2D: Dual Wake Phrase Support).

Enables reliable offline wake phrase detection for:
- "Hey OLIVER"
- "Hello OLIVER"
Preserves structured transcription metadata, genuine Vosk confidence, and the 0.25 threshold.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging
import re
import threading
import time
from typing import Optional

import speech_recognition as sr

from voice.audio_capture import AudioCapture
from voice.stt.base import SpeechToTextEngine, TranscriptionResult
from voice.stt.local_first import LocalFirstSTTEngine

WakeCallback = Callable[[], None]

# Default dual wake phrases
DEFAULT_WAKE_PHRASES: tuple[str, ...] = ("hey oliver", "hello oliver")


def normalize_wake_phrase(phrase: str) -> str:
    """Normalize a wake phrase: lowercase, collapse whitespace, strip punctuation."""
    if not isinstance(phrase, str):
        return ""
    clean = re.sub(r"[^\w\s]", " ", phrase.lower()).strip()
    return " ".join(clean.split())


class WakeWordDetector:
    """Listen for configured wake words/phrases in the background without persistent external audio transmission."""

    def __init__(
        self,
        wake_word: str = "hey oliver",
        wake_phrases: Optional[Iterable[str] | str] = None,
        logger: Optional[logging.Logger] = None,
        language: str = "en-US",
        stt_engine: Optional[SpeechToTextEngine] = None,
        cooldown_seconds: float = 2.0,
    ) -> None:
        self.language = language
        self.logger = logger or logging.getLogger(__name__)
        self._cooldown_seconds = max(0.1, float(cooldown_seconds))
        self._last_triggered_at = 0.0

        # Internal thread synchronization lock
        self._lock = threading.Lock()

        # Initialize wake phrases
        self.wake_phrases: list[str] = []
        if wake_phrases is not None:
            self.set_wake_phrases(wake_phrases)
        elif wake_word:
            clean_word = normalize_wake_phrase(wake_word)
            if clean_word == "hey oliver":
                self.set_wake_phrases(DEFAULT_WAKE_PHRASES)
            else:
                self.set_wake_phrases([clean_word])
        else:
            self.set_wake_phrases(DEFAULT_WAKE_PHRASES)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[WakeCallback] = None

        # Stage 2E: Microphone lifecycle coordination & reference-counted pause state
        self._state_lock = threading.RLock()
        self._pause_count = 0
        self._resume_event = threading.Event()
        self._resume_event.set()  # Initially unpaused
        self._pause_confirmed_event = threading.Event()

        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.4

        self.capture = AudioCapture(logger=self.logger)
        self.stt_engine = stt_engine or LocalFirstSTTEngine(
            fallback_external_allowed=False,  # Wake word detection should NEVER send continuous audio to external cloud
            logger=self.logger,
        )
        self.last_transcription_result: Optional[TranscriptionResult] = None

    @property
    def wake_word(self) -> str:
        """Backward compatibility for single wake word property."""
        with self._lock:
            return self.wake_phrases[0] if self.wake_phrases else "hey oliver"

    @wake_word.setter
    def wake_word(self, value: str) -> None:
        """Backward compatibility setter for wake word."""
        self.set_wake_word(value)

    @property
    def microphone(self) -> sr.Microphone:
        """Backward compatibility for microphone attribute."""
        return self.capture.get_microphone()

    def set_wake_word(self, wake_word: str) -> None:
        """Update or prepend primary wake word phrase."""
        norm = normalize_wake_phrase(wake_word)
        if not norm:
            return
        with self._lock:
            if norm not in self.wake_phrases:
                self.wake_phrases.insert(0, norm)
            else:
                self.wake_phrases.remove(norm)
                self.wake_phrases.insert(0, norm)

    def set_wake_phrases(self, phrases: Iterable[str] | str) -> None:
        """Configure multiple wake phrases (e.g. dual 'hey oliver', 'hello oliver')."""
        new_phrases: list[str] = []
        if isinstance(phrases, str):
            raw_list = phrases.split(",")
        elif isinstance(phrases, Iterable):
            raw_list = list(phrases)
        else:
            raw_list = []

        for p in raw_list:
            norm = normalize_wake_phrase(str(p))
            if norm and norm not in new_phrases:
                new_phrases.append(norm)

        # Safe fallback if input was empty or malformed
        if not new_phrases:
            new_phrases = list(DEFAULT_WAKE_PHRASES)

        with self._lock:
            self.wake_phrases = new_phrases

    @property
    def is_paused(self) -> bool:
        """True if wake detector capture is currently paused."""
        with self._state_lock:
            return self._pause_count > 0

    @property
    def is_alive(self) -> bool:
        """True if background detection thread is currently alive."""
        return self._thread is not None and self._thread.is_alive()

    def pause(self, timeout: float = 2.0) -> bool:
        """Pause wake-word microphone capture (thread-safe, reference-counted).

        Ensures background audio capture yields ownership of the microphone.
        Returns True if pause was confirmed or thread is not running; False if confirmation timed out.
        """
        with self._state_lock:
            self._pause_count += 1
            if self._pause_count > 1:
                # Already paused by previous request
                return True
            self._resume_event.clear()
            self._pause_confirmed_event.clear()

        # If background thread is not running, microphone is already free
        if not self.is_alive:
            with self._state_lock:
                self._pause_confirmed_event.set()
            return True

        # Wait for the background loop to confirm it is not actively capturing
        confirmed = self._pause_confirmed_event.wait(timeout=max(0.1, float(timeout)))
        if not confirmed:
            self.logger.warning("WakeWordDetector pause confirmation timed out (%.2fs)", timeout)
        return confirmed

    def resume(self, force: bool = False) -> None:
        """Resume wake-word microphone capture (thread-safe, reference-counted)."""
        with self._state_lock:
            if force:
                self._pause_count = 0
            elif self._pause_count > 0:
                self._pause_count -= 1

            if self._pause_count == 0:
                self._pause_confirmed_event.clear()
                self._resume_event.set()

    def start(self, callback: WakeCallback) -> None:
        """Start listening for wake word in background."""
        if self._thread and self._thread.is_alive():
            return

        self._callback = callback
        self._stop_event.clear()
        with self._state_lock:
            self._pause_count = 0
            self._resume_event.set()
            self._pause_confirmed_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            name="OliverWakeWordDetector",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop listening for wake word."""
        self._stop_event.set()
        # Ensure resume event is set so paused loop can exit cleanly
        self._resume_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        """Background wake word detection loop."""
        with self._lock:
            phrases_repr = ", ".join(f"'{p}'" for p in self.wake_phrases)
        self.logger.info("Wake word listener started (triggers: %s)", phrases_repr)

        while not self._stop_event.is_set():
            # Check pause state before microphone capture
            if self.is_paused:
                self._pause_confirmed_event.set()
                while self.is_paused and not self._stop_event.is_set():
                    self._resume_event.wait(timeout=0.1)
                if self._stop_event.is_set():
                    break
                self._pause_confirmed_event.clear()

            try:
                heard_text = self._listen_for_short_phrase()
                if not heard_text:
                    continue

                # Guard against firing if pause was requested during phrase capture
                if self.is_paused:
                    continue

                if self._contains_wake_word(heard_text):
                    self._trigger_callback()
            except sr.WaitTimeoutError:
                continue
            except Exception as exc:
                self.logger.debug("Wake word loop non-fatal event: %s", exc)
                time.sleep(0.3)

        self.logger.info("Wake word listener stopped")

    def _listen_for_short_phrase_result(self) -> TranscriptionResult:
        """Capture a short audio phrase and transcribe it locally, returning structured TranscriptionResult."""
        try:
            audio = self.capture.capture_audio(
                recognizer=self.recognizer,
                timeout=1.0,
                phrase_time_limit=2.5,
                ambient_duration=0.0,
            )
            result = self.stt_engine.transcribe(audio, language=self.language)
            self.last_transcription_result = result
            return result
        except sr.WaitTimeoutError:
            engine_name = getattr(self.stt_engine, "name", "vosk")
            empty_res = TranscriptionResult(
                text="", confidence=0.0, engine=engine_name, confidence_available=False
            )
            self.last_transcription_result = empty_res
            return empty_res
        except Exception as exc:
            self.logger.debug("Wake phrase capture non-fatal event: %s", exc)
            engine_name = getattr(self.stt_engine, "name", "vosk")
            err_res = TranscriptionResult(
                text="", confidence=0.0, engine=engine_name, confidence_available=False
            )
            self.last_transcription_result = err_res
            return err_res

    def _listen_for_short_phrase(self) -> str:
        """Capture a short audio phrase and return recognized text (backward-compatible plain string)."""
        result = self._listen_for_short_phrase_result()

        # Stage 2A compliance: Apply 0.25 threshold only when genuine confidence is available
        if result.confidence_available and result.confidence is not None:
            if result.confidence < 0.25 and result.text:
                self.logger.warning(
                    "Wake detector received low-confidence transcript (%.2f): '%s'; ignoring",
                    result.confidence,
                    result.text,
                )
                return ""

        return result.text.lower().strip()

    def _contains_wake_word(self, text: str) -> bool:
        """Check if transcribed phrase contains any configured wake phrase as a contiguous token sequence."""
        if not isinstance(text, str) or not text.strip():
            return False

        with self._lock:
            phrases_to_check = list(self.wake_phrases)

        if not phrases_to_check:
            return False

        # Tokenize input text (punctuation replaced with space, collapsed whitespace)
        clean_input = re.sub(r"[^\w\s]", " ", text.lower()).strip()
        tokens = clean_input.split()
        if not tokens:
            return False

        for phrase in phrases_to_check:
            phrase_tokens = phrase.split()
            phrase_len = len(phrase_tokens)
            if phrase_len == 0 or len(tokens) < phrase_len:
                continue

            # Exact contiguous sub-sequence match
            for i in range(len(tokens) - phrase_len + 1):
                if tokens[i : i + phrase_len] == phrase_tokens:
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
