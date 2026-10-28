"""High-level service coordinating productivity store, scheduler, voice dispatch, and daily briefing."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

from core.config import OliverConfig, get_config
from memory.unified_db import UnifiedDatabase, get_unified_db
from productivity.datetime_parser import DateTimeParser
from productivity.models import DailyPlan, NoteItem, ReminderItem, TaskItem
from productivity.scheduler import ProductivityScheduler
from productivity.store import ProductivityStore

logger = logging.getLogger("oliver.productivity.service")


class ProductivityService:
    """Coordinates productivity domain logic, background scheduler, and AI briefing."""

    def __init__(
        self,
        config: Optional[OliverConfig] = None,
        db: Optional[UnifiedDatabase] = None,
        speaker: Optional[Any] = None,
        start_scheduler: bool = True,
    ) -> None:
        self.config = config if config is not None else get_config()
        self.db = db if db is not None else get_unified_db()
        self.store = ProductivityStore(self.db)
        self.speaker = speaker
        self._dispatch_listeners: list[Callable[[ReminderItem], None]] = []
        self._listeners_lock = threading.Lock()

        prod_cfg = self.config.productivity
        self.scheduler = ProductivityScheduler(
            store=self.store,
            poll_interval=prod_cfg.scheduler_interval_seconds,
            lease_seconds=prod_cfg.lease_duration_seconds,
            max_retries=prod_cfg.max_dispatch_retries,
            grace_hours=prod_cfg.missed_grace_hours,
            dispatch_callback=self._handle_reminder_dispatch,
        )

        if prod_cfg.enabled and start_scheduler:
            self.scheduler.start()

    def add_dispatch_listener(self, callback: Callable[[ReminderItem], None]) -> None:
        """Register a callback for reminder dispatch events."""
        with self._listeners_lock:
            if callback not in self._dispatch_listeners:
                self._dispatch_listeners.append(callback)

    def remove_dispatch_listener(self, callback: Callable[[ReminderItem], None]) -> None:
        """Unregister a dispatch callback."""
        with self._listeners_lock:
            if callback in self._dispatch_listeners:
                self._dispatch_listeners.remove(callback)

    def list_reminders(self, status: Optional[str] = None) -> list[ReminderItem]:
        """List reminders from store."""
        return self.store.list_reminders(status=status)

    def acknowledge_reminder(self, reminder_id: int) -> Optional[ReminderItem]:
        """Acknowledge a reminder idempotently."""
        return self.store.acknowledge_reminder(reminder_id)

    def complete_reminder(self, reminder_id: int) -> Optional[ReminderItem]:
        """Mark a reminder completed idempotently."""
        return self.store.complete_reminder(reminder_id)

    def _handle_reminder_dispatch(self, reminder: ReminderItem) -> bool:
        """Default reminder dispatch handler: speaks via SAPI5, notifies listeners, and logs."""
        alert_text = f"Reminder: {reminder.title}"
        logger.info("[PRODUCTIVITY DISPATCH] %s (Remind at: %s)", alert_text, reminder.remind_at)

        # Notify all registered listeners with exception isolation
        with self._listeners_lock:
            listeners = list(self._dispatch_listeners)
        for listener in listeners:
            try:
                listener(reminder)
            except Exception as exc:
                logger.warning("Reminder dispatch listener raised exception: %s", exc)

        if self.speaker and hasattr(self.speaker, "speak"):
            try:
                self.speaker.speak(alert_text, wait=False)
            except Exception as spk_err:
                logger.warning("Voice playback failed during reminder dispatch: %s", spk_err)

        return True

    def shutdown(self) -> None:
        """Stop background scheduler."""
        if self.scheduler.is_running():
            self.scheduler.stop()

    # -------------------------------------------------------------------------
    # DAILY PLAN & LLM BRIEFING
    # -------------------------------------------------------------------------

    def get_daily_plan(self, target_date_iso: Optional[str] = None) -> DailyPlan:
        """Generate an aggregated daily agenda with briefing summary."""
        now_dt = DateTimeParser.now_local()
        date_str = target_date_iso or DateTimeParser.to_iso(now_dt)

        tasks_due, reminders_due, overdue_tasks, overdue_reminders = self.store.get_daily_items(date_str)

        # Build fallback plain-text summary
        summary_lines = [f"Daily Plan for {date_str[:10]}:"]
        if tasks_due:
            summary_lines.append(f"- Tasks due today ({len(tasks_due)}): " + ", ".join(t.title for t in tasks_due[:5]))
        else:
            summary_lines.append("- No tasks due today.")

        if reminders_due:
            summary_lines.append(f"- Reminders scheduled ({len(reminders_due)}): " + ", ".join(r.title for r in reminders_due[:5]))
        else:
            summary_lines.append("- No reminders scheduled today.")

        if overdue_tasks:
            summary_lines.append(f"- Overdue tasks ({len(overdue_tasks)}): " + ", ".join(t.title for t in overdue_tasks[:3]))

        if overdue_reminders:
            summary_lines.append(f"- Overdue reminders ({len(overdue_reminders)}): " + ", ".join(r.title for r in overdue_reminders[:3]))

        summary_text = "\n".join(summary_lines)

        # Attempt Ollama local briefing synthesis if enabled and available
        try:
            from llm.ollama_client import OllamaClient
            client = OllamaClient()
            if client.is_available():
                prompt = (
                    "You are Oliver, a personal AI productivity assistant. "
                    "Write a crisp, motivating 2-sentence morning briefing summarizing this schedule:\n"
                    f"{summary_text}\n"
                    "Keep it encouraging, concise, and focused on top priorities."
                )
                ai_resp = client.generate(prompt)
                if ai_resp and ai_resp.strip():
                    summary_text = f"{ai_resp.strip()}\n\nDetails:\n{summary_text}"
        except Exception as llm_err:
            logger.debug("Ollama briefing synthesis skipped: %s", llm_err)

        return DailyPlan(
            date=date_str,
            tasks_due=tasks_due,
            reminders_due=reminders_due,
            overdue_tasks=overdue_tasks,
            overdue_reminders=overdue_reminders,
            summary_text=summary_text,
        )


_global_service: Optional[ProductivityService] = None


def get_productivity_service() -> ProductivityService:
    """Return the global ProductivityService singleton."""
    global _global_service
    if _global_service is None:
        _global_service = ProductivityService()
    return _global_service
