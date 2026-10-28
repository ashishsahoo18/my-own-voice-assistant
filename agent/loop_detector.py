"""Loop and oscillation detection to prevent runaway agent execution and repeated destructive actions."""

from __future__ import annotations

import json
from collections import deque
from typing import Any, Optional
from core.logging import get_logger

logger = get_logger("agent.loop_detector")


class LoopDetectedError(Exception):
    """Raised when the agent attempts a loop or repeats an identical/destructive action."""


class LoopDetector:
    """Monitors action sequences for loops, oscillation, and repeated destructive operations."""

    DESTRUCTIVE_TOOLS = {
        "files.delete_file",
        "files.delete_folder",
        "windows.shutdown",
        "windows.restart",
        "memory.forget",
    }

    def __init__(self, window_size: int = 5) -> None:
        self.window_size = window_size
        self._history: deque[tuple[str, str]] = deque(maxlen=window_size)
        self._destructive_counts: dict[str, int] = {}

    def _normalize_args(self, args: dict[str, Any]) -> str:
        """Create a deterministic JSON string representation of tool arguments."""
        try:
            return json.dumps(args, sort_keys=True, default=str)
        except Exception:
            return str(sorted(args.items()))

    def check_and_record(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        """Check if executing this tool with these arguments creates a loop or policy violation.

        Returns:
            (is_loop, reason_if_any)
        """
        args_str = self._normalize_args(arguments)
        current_action = (tool_name, args_str)

        # 1. Immediate identical repeat check
        if self._history and self._history[-1] == current_action:
            reason = f"Immediate duplicate action detected: repeated '{tool_name}' with identical arguments."
            logger.warning(reason)
            return True, reason

        # 2. Oscillatory loop check (e.g., A -> B -> A -> B)
        if len(self._history) >= 3:
            h_list = list(self._history)
            # Check for pattern A, B, A, B
            if len(h_list) >= 3 and h_list[-2] == current_action:
                reason = f"Oscillating loop detected: repeating action sequence with '{tool_name}'."
                logger.warning(reason)
                return True, reason

        # 3. Repeated destructive action check
        if tool_name in self.DESTRUCTIVE_TOOLS:
            cnt = self._destructive_counts.get(tool_name, 0)
            if cnt >= 1:
                # Disallow repeating destructive action in the same multi-step task
                reason = f"Repeated destructive action blocked: '{tool_name}' has already been executed in this task."
                logger.warning(reason)
                return True, reason
            self._destructive_counts[tool_name] = cnt + 1

        # Safe: record action in history
        self._history.append(current_action)
        return False, ""

    def check_or_raise(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Check action and raise LoopDetectedError if a loop or repeated destructive action is detected."""
        is_loop, reason = self.check_and_record(tool_name, arguments)
        if is_loop:
            raise LoopDetectedError(reason)

    def reset(self) -> None:
        """Reset history for a fresh task."""
        self._history.clear()
        self._destructive_counts.clear()
