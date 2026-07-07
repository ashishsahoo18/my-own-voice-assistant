import logging
import threading
from typing import Callable, Optional

import speech_recognition as sr


class WakeWordDetector:
    """Listen for a configured wake word in the background."""

    def __init__(self, wake_word: str = "hey ayra", logger: Optional[logging.Logger] = None) -> None:
        self.wake_word = wake_word.lower().strip()
        self.logger = logger
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[], None]] = None
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

    def set_wake_word(self, wake_word: str) -> None:
        self.wake_word = wake_word.lower().strip()

    def start(self, callback: Callable[[], None]) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._callback = callback
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=1)
                text = self.recognizer.recognize_google(audio, language="en-US").lower()
                if self.wake_word and self.wake_word in text:
                    if self.logger is not None:
                        self.logger.info("Wake word detected")
                    if self._callback is not None:
                        self._callback()
            except sr.UnknownValueError:
                continue
            except sr.WaitTimeoutError:
                continue
            except Exception as exc:  # pragma: no cover - defensive guard
                if self.logger is not None:
                    self.logger.error("Wake word detection error: %s", exc)
                continue
