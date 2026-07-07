from __future__ import annotations

import time
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional


class ProductivityCommands:
    """Simple productivity helpers for calculator, timer, planner, and notes."""

    def __init__(self) -> None:
        self._stopwatch_started_at: Optional[float] = None
        self._countdown_running = False

    def calculate(self, expression: str) -> str:
        try:
            return str(eval(expression, {"__builtins__": {}}, {}))
        except Exception as exc:
            return f"Calculation error: {exc}"

    def start_stopwatch(self) -> str:
        self._stopwatch_started_at = time.time()
        return "Stopwatch started."

    def stop_stopwatch(self) -> str:
        if self._stopwatch_started_at is None:
            return "Stopwatch was not running."
        elapsed = time.time() - self._stopwatch_started_at
        self._stopwatch_started_at = None
        return f"Stopwatch stopped after {elapsed:.1f} seconds."

    def start_countdown(self, seconds: int) -> str:
        self._countdown_running = True
        Thread(target=self._run_countdown, args=(seconds,), daemon=True).start()
        return f"Countdown started for {seconds} seconds."

    def _run_countdown(self, seconds: int) -> None:
        time.sleep(seconds)
        self._countdown_running = False

    def pomodoro_timer(self, minutes: int = 25) -> str:
        return f"Pomodoro timer started for {minutes} minutes."

    def daily_planner(self, task: str) -> str:
        return f"Planned: {task}"

    def quick_note(self, note: str) -> str:
        return f"Saved note: {note}"

    def todo_list(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)
