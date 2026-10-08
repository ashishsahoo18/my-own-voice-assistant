"""Emergency kill switch and rate limiting for OLIVER 2.0."""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from typing import Optional

from core.logging import get_audit_logger
from security.confirmation import get_confirmation_manager


class KillSwitch:
    """Thread-safe emergency kill switch for immediate action halting."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._is_active = False
        self._reason = ""

    def activate(self, reason: str = "Emergency kill switch triggered") -> None:
        """Immediately engage kill switch, abort pending tasks, and invalidate tokens."""
        with self._lock:
            self._is_active = True
            self._reason = reason

            # Invalidate all pending confirmation tokens immediately
            cm = get_confirmation_manager()
            count = cm.invalidate_all(reason)

            # Audit record
            audit = get_audit_logger()
            audit.record_event(
                event_type="KILL_SWITCH_ACTIVATED",
                action="kill_switch",
                risk_level=3,
                status="ENGAGED",
                details={"reason": reason, "invalidated_tokens": count},
            )

    def deactivate(self) -> None:
        """Deactivate kill switch and restore normal operations."""
        with self._lock:
            self._is_active = False
            self._reason = ""

            audit = get_audit_logger()
            audit.record_event(
                event_type="KILL_SWITCH_DEACTIVATED",
                action="kill_switch",
                risk_level=0,
                status="DISENGAGED",
            )

    @property
    def is_active(self) -> bool:
        """Return True if kill switch is currently engaged."""
        return self._is_active

    @property
    def reason(self) -> str:
        """Return reason why kill switch was engaged."""
        return self._reason


class RateLimiter:
    """Sliding-window rate limiter for sensitive actions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: dict[str, list[float]] = defaultdict(list)

    def allow(
        self,
        key: str,
        max_requests: int = 5,
        window_seconds: float = 60.0,
    ) -> bool:
        """Return True if operation is within rate limit; otherwise False."""
        now = time.time()
        with self._lock:
            timestamps = self._history[key]
            # Prune timestamps older than window
            cutoff = now - window_seconds
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._history[key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                return False

            self._history[key].append(now)
            return True


_global_kill_switch: Optional[KillSwitch] = None
_global_rate_limiter: Optional[RateLimiter] = None


def get_kill_switch() -> KillSwitch:
    """Return kill switch singleton."""
    global _global_kill_switch
    if _global_kill_switch is None:
        _global_kill_switch = KillSwitch()
    return _global_kill_switch


def get_rate_limiter() -> RateLimiter:
    """Return rate limiter singleton."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter
