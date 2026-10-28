"""Voice pipeline state definitions and state-machine observer for OLIVER 2.0."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from enum import Enum
from typing import Optional


class VoiceState(str, Enum):
    """Explicit voice pipeline lifecycle states."""

    READY = "READY"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    EXECUTING = "EXECUTING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


StateChangeCallback = Callable[[VoiceState, Optional[str]], None]


class VoiceStateMachine:
    """Thread-safe state manager with listener notifications."""

    def __init__(self, initial_state: VoiceState = VoiceState.READY, logger: Optional[logging.Logger] = None) -> None:
        self._current_state = initial_state
        self._lock = threading.RLock()
        self._listeners: list[StateChangeCallback] = []
        self._logger = logger or logging.getLogger(__name__)

    @property
    def current_state(self) -> VoiceState:
        """Get the current voice state."""
        with self._lock:
            return self._current_state

    def transition_to(self, new_state: VoiceState, detail: Optional[str] = None) -> VoiceState:
        """Atomically transition to a new voice state and notify observers."""
        with self._lock:
            old_state = self._current_state
            if old_state == new_state and detail is None:
                return self._current_state

            self._current_state = new_state
            self._logger.info("VoiceState transition: %s -> %s (%s)", old_state.value, new_state.value, detail or "nominal")
            listeners_copy = list(self._listeners)

        for listener in listeners_copy:
            try:
                listener(new_state, detail)
            except Exception as exc:
                self._logger.warning("Error in VoiceState listener: %s", exc)

        return self._current_state

    def add_listener(self, callback: StateChangeCallback) -> None:
        """Register a state change listener."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: StateChangeCallback) -> None:
        """Remove a registered state change listener."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)
