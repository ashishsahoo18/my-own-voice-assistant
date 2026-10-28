"""Interruptible Text-to-speech speaker for OLIVER 2.0 with safe barge-in support."""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections.abc import Callable
from typing import Any, Optional

import pyttsx3


class VoiceSpeaker:
    """Thread-safe, interruptible speech synthesizer with safe barge-in support."""

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: int = 170,
        volume: float = 1.0,
        on_speaking_changed: Optional[Callable[[bool], None]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.voice_id = voice
        self.rate = max(80, min(300, rate))
        self.volume = max(0.0, min(1.0, volume))
        self.on_speaking_changed = on_speaking_changed
        self.logger = logger or logging.getLogger(__name__)

        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self._is_speaking = False
        self._queue: queue.Queue[Optional[tuple[str, threading.Event]]] = queue.Queue()

        self.engine: Optional[Any] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._start_worker()

    @property
    def is_speaking(self) -> bool:
        """Return True if speaker is actively generating audio output."""
        with self._lock:
            return self._is_speaking

    def _start_worker(self) -> None:
        """Start the dedicated synthesis worker thread."""
        self._worker_thread = threading.Thread(
            target=self._speech_loop,
            name="OliverVoiceSpeakerWorker",
            daemon=True,
        )
        self._worker_thread.start()

    def _speech_loop(self) -> None:
        """Dedicated thread loop for pyttsx3/SAPI5 COM stability."""
        try:
            self.engine = pyttsx3.init()
            self._configure_voice()
        except Exception as exc:
            self.logger.warning("Text-to-speech engine initialization failed; muted: %s", exc)
            self.engine = None

        while True:
            try:
                task = self._queue.get()
                if task is None:
                    break

                text, done_event = task
                if self._stopped.is_set():
                    done_event.set()
                    self._queue.task_done()
                    continue

                self._set_speaking_state(True)
                self._speak_text_internal(text)
                self._set_speaking_state(False)

                done_event.set()
                self._queue.task_done()
            except Exception as exc:
                self.logger.error("Speech loop error: %s", exc)
                self._set_speaking_state(False)

    def _set_speaking_state(self, is_speaking: bool) -> None:
        """Update speaking state and notify callback."""
        with self._lock:
            if self._is_speaking == is_speaking:
                return
            self._is_speaking = is_speaking

        if self.on_speaking_changed:
            try:
                self.on_speaking_changed(is_speaking)
            except Exception as exc:
                self.logger.warning("Error in on_speaking_changed callback: %s", exc)

    def _configure_voice(self) -> None:
        """Apply voice, rate, and volume settings to the engine."""
        if self.engine is None:
            return

        try:
            voices = self.engine.getProperty("voices")
            preferred = self.voice_id

            if preferred:
                for v in voices:
                    if getattr(v, "id", "") == preferred:
                        self.engine.setProperty("voice", v.id)
                        break
            else:
                self._select_default_female_voice(voices)

            self.engine.setProperty("rate", self.rate)
            self.engine.setProperty("volume", self.volume)
        except Exception as exc:
            self.logger.warning("Could not apply voice properties: %s", exc)

    def _select_default_female_voice(self, voices: list[Any]) -> None:
        """Prefer a female English Windows voice when available."""
        if self.engine is None:
            return

        preferred_keywords = ["zira", "female", "susan", "hazel", "samantha"]
        for voice in voices:
            searchable = f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".lower()
            if any(keyword in searchable for keyword in preferred_keywords):
                self.engine.setProperty("voice", voice.id)
                return

    def set_voice(self, voice_id: str) -> None:
        """Set voice by engine voice ID."""
        with self._lock:
            self.voice_id = voice_id or None
            self._configure_voice()

    def get_available_voices(self) -> list[dict[str, str]]:
        """Return available installed system voices."""
        if self.engine is None:
            return []

        voices = []
        try:
            for voice in self.engine.getProperty("voices"):
                voices.append({
                    "id": str(getattr(voice, "id", "")),
                    "name": str(getattr(voice, "name", "")),
                })
        except Exception as exc:
            self.logger.warning("Failed to enumerate voices: %s", exc)

        return voices

    def set_rate(self, rate: int) -> None:
        """Set speech speed."""
        with self._lock:
            self.rate = max(80, min(300, rate))
            if self.engine is not None:
                try:
                    self.engine.setProperty("rate", self.rate)
                except Exception:
                    pass

    def set_volume(self, volume: float) -> None:
        """Set speech volume."""
        with self._lock:
            self.volume = max(0.0, min(1.0, volume))
            if self.engine is not None:
                try:
                    self.engine.setProperty("volume", self.volume)
                except Exception:
                    pass

    def speak(self, text: str, wait: bool = False) -> None:
        """Enqueue text for speech synthesis.
        
        If wait is True, blocks until utterance completes or is interrupted.
        """
        clean_text = self._clean_text_for_speech(text)
        if not clean_text or self.engine is None:
            return

        with self._lock:
            if self._stopped.is_set():
                self._stopped.clear()

        done_event = threading.Event()
        self._queue.put((clean_text, done_event))

        if wait:
            done_event.wait()

    def _speak_text_internal(self, text: str) -> None:
        """Run speech synthesis, broken into sentences for fast interruption."""
        if self.engine is None or not text:
            return

        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            if self._stopped.is_set():
                break

            s_clean = sentence.strip()
            if not s_clean:
                continue

            try:
                self.engine.say(s_clean)
                self.engine.runAndWait()
            except RuntimeError as exc:
                self.logger.warning("Speech runtime error: %s", exc)
                break
            except Exception as exc:
                self.logger.warning("Speech output failed: %s", exc)
                break

    def stop(self) -> None:
        """Immediately stop and clear all pending speech output."""
        self._stopped.set()

        # Clear remaining queue items
        while not self._queue.empty():
            try:
                task = self._queue.get_nowait()
                if task is not None:
                    task[1].set()
                self._queue.task_done()
            except Exception:
                break

        with self._lock:
            if self.engine is not None:
                try:
                    self.engine.stop()
                except Exception:
                    pass
            self._set_speaking_state(False)

    def barge_in(self) -> None:
        """Safe barge-in handler: immediately halts speech when user initiates input."""
        self.logger.info("Barge-in triggered; stopping ongoing speech output.")
        self.stop()

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