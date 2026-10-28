"""Thread-safe UI Event Bridge for OLIVER 2.0.

Provides a synchronized queue-based bridge between background worker threads
and the Tkinter/CustomTkinter main thread. Background threads enqueue callable
events, and only the main GUI thread executes them via bounded after() polling.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable, Optional


logger = logging.getLogger("oliver.ui.event_bridge")


class UIEventQueue:
    """Thread-safe event bridge with bounded polling and safe shutdown semantics."""

    def __init__(
        self,
        poll_interval_ms: int = 25,
        max_events_per_poll: int = 50,
        logger_instance: Optional[logging.Logger] = None,
    ) -> None:
        self.poll_interval_ms = poll_interval_ms
        self.max_events_per_poll = max_events_per_poll
        self.logger = logger_instance or logger

        self._queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = queue.Queue()
        self._lock = threading.RLock()
        self._accepting_events = True
        self._root: Any = None
        self._poll_job: Optional[str] = None
        self._is_polling = False
        self._main_thread_id: Optional[int] = None
        self._discarded_count = 0
        self._processed_count = 0

    @property
    def is_accepting(self) -> bool:
        """Return True if the bridge is currently accepting new events."""
        with self._lock:
            return self._accepting_events

    @property
    def is_polling(self) -> bool:
        """Return True if the recurring polling loop is active."""
        with self._lock:
            return self._is_polling

    @property
    def pending_count(self) -> int:
        """Return the number of events currently waiting in the queue."""
        return self._queue.qsize()

    @property
    def discarded_count(self) -> int:
        """Return the total number of events rejected or discarded after bridge closure."""
        with self._lock:
            return self._discarded_count

    @property
    def processed_count(self) -> int:
        """Return the total number of events processed by the main thread."""
        with self._lock:
            return self._processed_count

    def bind_root(self, root: Any) -> None:
        """Bind the Tkinter/CustomTkinter root window and record main thread ID."""
        with self._lock:
            self._root = root
            self._main_thread_id = threading.get_ident()

    def start_polling(self) -> None:
        """Start recurring main-thread polling loop if bound to a live root."""
        with self._lock:
            if not self._accepting_events:
                self.logger.warning("Cannot start polling on a closed UIEventQueue.")
                return
            if self._is_polling:
                return
            self._is_polling = True

        self._schedule_poll()

    def _schedule_poll(self) -> None:
        """Schedule next poll callback on root if root is alive and polling is active."""
        with self._lock:
            if not self._is_polling or not self._accepting_events or self._root is None:
                return

        try:
            self._poll_job = self._root.after(self.poll_interval_ms, self._poll_tick)
        except Exception as exc:
            self.logger.warning("Failed to schedule UI event poll tick: %s", exc)
            with self._lock:
                self._is_polling = False
                self._poll_job = None

    def _poll_tick(self) -> None:
        """Invoked by Tkinter main thread on timer tick to process pending events."""
        with self._lock:
            self._poll_job = None
            if not self._is_polling or not self._accepting_events:
                return

        try:
            self.process_events(max_events=self.max_events_per_poll)
        finally:
            with self._lock:
                if self._is_polling and self._accepting_events:
                    self._schedule_poll()

    def post(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Enqueue a callback to be executed on the UI main thread.

        Thread-safe: can be called from any thread (background worker, audio thread, etc.).

        Returns:
            True if event was accepted into queue, False if rejected (bridge closed).
        """
        with self._lock:
            if not self._accepting_events:
                self._discarded_count += 1
                self.logger.warning(
                    "UIEventQueue rejected event %r after bridge closure (discarded=%d)",
                    getattr(callback, "__name__", repr(callback)),
                    self._discarded_count,
                )
                return False

        self._queue.put((callback, args, kwargs))
        return True

    def process_events(self, max_events: Optional[int] = None) -> int:
        """Process up to max_events from the queue on the calling thread.

        Must be executed from the Tkinter main thread.
        Callback exceptions are caught, logged, and isolated to prevent crashing the UI loop.

        Returns:
            The number of events successfully executed or handled.
        """
        limit = max_events if max_events is not None else self.max_events_per_poll
        handled = 0

        while handled < limit:
            try:
                callback, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                break

            # If the bridge was closed while this item was queued, discard safely
            with self._lock:
                if not self._accepting_events:
                    self._discarded_count += 1
                    self.logger.debug(
                        "Discarding queued event %r because bridge is closed",
                        getattr(callback, "__name__", repr(callback)),
                    )
                    continue

            handled += 1
            with self._lock:
                self._processed_count += 1

            try:
                callback(*args, **kwargs)
            except Exception as exc:
                self.logger.exception(
                    "Unhandled exception in UI event callback %r: %s",
                    getattr(callback, "__name__", repr(callback)),
                    exc,
                )

        return handled

    def shutdown(self) -> int:
        """Safely close the event bridge and discard any pending events.

        1. Immediately stops accepting new events (`post()` will return False).
        2. Cancels any pending `after()` polling callback on root.
        3. Drains remaining queued events without executing callbacks, preventing
           access to widgets about to be destroyed.

        Returns:
            The number of remaining events drained and discarded.
        """
        with self._lock:
            self._accepting_events = False
            self._is_polling = False

            if self._root is not None and self._poll_job is not None:
                try:
                    self._root.after_cancel(self._poll_job)
                except Exception as exc:
                    self.logger.debug("after_cancel error during shutdown: %s", exc)
                finally:
                    self._poll_job = None

        # Drain remaining events
        drained = 0
        while True:
            try:
                _ = self._queue.get_nowait()
                drained += 1
            except queue.Empty:
                break

        with self._lock:
            self._discarded_count += drained

        self.logger.info("UIEventQueue shut down: %d pending events drained/discarded", drained)
        return drained
