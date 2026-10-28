"""Background daemon scheduler for due reminders with atomic leases and crash recovery."""

from __future__ import annotations

import atexit
import logging
import os
import sqlite3
import threading
import time
import uuid
from typing import Callable, Optional

from productivity.datetime_parser import DateTimeParser
from productivity.models import ReminderItem
from productivity.store import ProductivityStore

logger = logging.getLogger("oliver.productivity.scheduler")


class ProductivityScheduler:
    """Single-instance daemon thread for polling and dispatching due reminders."""

    def __init__(
        self,
        store: ProductivityStore,
        poll_interval: float = 5.0,
        lease_seconds: float = 30.0,
        max_retries: int = 3,
        grace_hours: float = 24.0,
        dispatch_callback: Optional[Callable[[ReminderItem], bool]] = None,
    ) -> None:
        self.store = store
        self.poll_interval = max(1.0, poll_interval)
        self.lease_seconds = max(5.0, lease_seconds)
        self.max_retries = max(1, max_retries)
        self.grace_hours = max(1.0, grace_hours)
        self.dispatch_callback = dispatch_callback

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._recovery_executed = False

        atexit.register(self.stop)

    def start(self) -> None:
        """Start the background scheduler thread if not already running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.debug("ProductivityScheduler is already running.")
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="OliverProductivityScheduler",
                daemon=True,
            )
            self._thread.start()
            logger.info("ProductivityScheduler daemon thread started (interval=%.1fs).", self.poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the scheduler loop to terminate and wait for thread to exit."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return

            self._stop_event.set()
            thread = self._thread

        thread.join(timeout=timeout)
        logger.info("ProductivityScheduler terminated.")

    def is_running(self) -> bool:
        """Check whether the scheduler thread is alive."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def _run_loop(self) -> None:
        """Main scheduler loop running until stopped."""
        worker_id = f"oliver_{os.getpid()}_{threading.get_ident()}_{uuid.uuid4().hex[:6]}"
        logger.debug("Scheduler worker ID initialized: %s", worker_id)

        # 1. Run startup recovery on initial boot
        if not self._recovery_executed:
            try:
                now_iso = DateTimeParser.to_iso(DateTimeParser.now_local())
                stats = self.store.recover_startup_reminders(now_iso, grace_hours=self.grace_hours)
                logger.info("Startup reminder recovery completed: %s", stats)
                self._recovery_executed = True
            except Exception as rec_err:
                logger.warning("Startup recovery encountered error: %s", rec_err)

        # 2. Main polling loop
        backoff_delay = 0.5
        while not self._stop_event.is_set():
            try:
                self._poll_and_dispatch(worker_id)
                backoff_delay = 0.5  # reset on success
            except sqlite3.OperationalError as op_err:
                if "locked" in str(op_err).lower() or "busy" in str(op_err).lower():
                    logger.warning("Database locked during scheduler poll. Backing off %.1fs: %s", backoff_delay, op_err)
                    time.sleep(backoff_delay)
                    backoff_delay = min(5.0, backoff_delay * 2.0)
                else:
                    logger.error("SQLite error in scheduler loop: %s", op_err)
            except Exception as exc:
                logger.error("Unexpected error in scheduler loop: %s", exc, exc_info=True)

            self._stop_event.wait(self.poll_interval)

    def _poll_and_dispatch(self, worker_id: str) -> None:
        """Poll due reminders, acquire atomic leases, and execute dispatch."""
        now_dt = DateTimeParser.now_local()
        now_iso = DateTimeParser.to_iso(now_dt)

        claimed = self.store.claim_due_reminders(
            worker_id=worker_id,
            now_iso=now_iso,
            lease_seconds=self.lease_seconds,
            limit=10,
        )

        for reminder in claimed:
            if self._stop_event.is_set():
                break

            logger.info("Scheduler claimed due reminder %s: '%s'", reminder.id, reminder.title)
            success = False
            error_msg: Optional[str] = None

            try:
                if self.dispatch_callback:
                    success = bool(self.dispatch_callback(reminder))
                else:
                    logger.warning("No dispatch callback registered for reminder %s; logging only.", reminder.id)
                    success = True
            except Exception as cb_exc:
                error_msg = str(cb_exc)
                logger.error("Dispatch callback failed for reminder %s: %s", reminder.id, cb_exc)

            if success:
                self.store.mark_dispatched(
                    reminder_id=reminder.id,
                    worker_id=worker_id,
                    channels=["voice", "ui"],
                    now_iso=now_iso,
                )
                logger.info("Reminder %s marked DISPATCHED.", reminder.id)
            else:
                err_text = error_msg or "DispatchCallbackReturnedFalse"
                self.store.mark_dispatch_failed(
                    reminder_id=reminder.id,
                    worker_id=worker_id,
                    error=err_text,
                    max_retries=self.max_retries,
                    now_iso=now_iso,
                )
                logger.warning("Reminder %s dispatch failed (attempt %d).", reminder.id, reminder.dispatch_attempts + 1)
