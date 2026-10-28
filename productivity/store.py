"""Persistent storage operations for tasks, reminders, and notes using UnifiedDatabase."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional, Tuple

from memory.unified_db import UnifiedDatabase, get_unified_db
from productivity.datetime_parser import DateTimeParser
from productivity.models import (
    DailyPlan,
    NoteItem,
    RecurrenceType,
    ReminderItem,
    ReminderStatus,
    TaskItem,
    TaskPriority,
    TaskStatus,
)
from productivity.recurrence import RecurrenceEngine

logger = logging.getLogger("oliver.productivity.store")


class ProductivityStore:
    """Manages transactional database access for all productivity domain items."""

    def __init__(self, db: Optional[UnifiedDatabase] = None) -> None:
        self.db = db if db is not None else get_unified_db()

    # -------------------------------------------------------------------------
    # TASKS REPOSITORY
    # -------------------------------------------------------------------------

    def create_task(
        self,
        title: str,
        description: str = "",
        due_date: Optional[str] = None,
        priority: str = TaskPriority.NORMAL.value,
        metadata_json: str = "{}",
    ) -> TaskItem:
        """Create a new user task."""
        if not title or not title.strip():
            raise ValueError("Task title cannot be empty.")

        clean_priority = priority.lower().strip()
        if clean_priority not in [p.value for p in TaskPriority]:
            clean_priority = TaskPriority.NORMAL.value

        now_iso = DateTimeParser.to_iso(DateTimeParser.now_local())
        clean_due = None
        if due_date:
            parsed = DateTimeParser.parse(due_date)
            clean_due = DateTimeParser.to_iso(parsed)

        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO user_tasks (title, description, due_date, priority, status, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    description.strip(),
                    clean_due,
                    clean_priority,
                    TaskStatus.PENDING.value,
                    now_iso,
                    metadata_json,
                ),
            )
            task_id = cur.lastrowid

        return self.get_task(task_id)  # type: ignore[return-value]

    def get_task(self, task_id: int) -> Optional[TaskItem]:
        """Retrieve a task by ID."""
        row = self.db.fetch_one(
            """
            SELECT id, title, description, due_date, priority, status, created_at, completed_at, metadata_json
            FROM user_tasks WHERE id = ?
            """,
            (task_id,),
        )
        if not row:
            return None
        return TaskItem(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            due_date=row["due_date"],
            priority=row["priority"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            metadata_json=row["metadata_json"] or "{}",
        )

    def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 50,
    ) -> List[TaskItem]:
        """List tasks with optional status and priority filtering."""
        query = "SELECT id, title, description, due_date, priority, status, created_at, completed_at, metadata_json FROM user_tasks WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status.lower().strip())
        if priority:
            query += " AND priority = ?"
            params.append(priority.lower().strip())

        query += " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 ELSE 5 END, due_date ASC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(query, tuple(params))
        return [
            TaskItem(
                id=r["id"],
                title=r["title"],
                description=r["description"] or "",
                due_date=r["due_date"],
                priority=r["priority"],
                status=r["status"],
                created_at=r["created_at"],
                completed_at=r["completed_at"],
                metadata_json=r["metadata_json"] or "{}",
            )
            for r in rows
        ]

    def update_task(
        self,
        task_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[TaskItem]:
        """Update existing task fields."""
        task = self.get_task(task_id)
        if not task:
            return None

        updates: list[str] = []
        params: list[Any] = []

        if title is not None:
            if not title.strip():
                raise ValueError("Task title cannot be empty.")
            updates.append("title = ?")
            params.append(title.strip())

        if description is not None:
            updates.append("description = ?")
            params.append(description.strip())

        if due_date is not None:
            if due_date == "":
                updates.append("due_date = NULL")
            else:
                parsed = DateTimeParser.parse(due_date)
                updates.append("due_date = ?")
                params.append(DateTimeParser.to_iso(parsed))

        if priority is not None:
            clean_p = priority.lower().strip()
            if clean_p in [p.value for p in TaskPriority]:
                updates.append("priority = ?")
                params.append(clean_p)

        if status is not None:
            clean_s = status.lower().strip()
            if clean_s in [s.value for s in TaskStatus]:
                updates.append("status = ?")
                params.append(clean_s)
                if clean_s == TaskStatus.COMPLETED.value:
                    updates.append("completed_at = ?")
                    params.append(DateTimeParser.to_iso(DateTimeParser.now_local()))

        if not updates:
            return task

        params.append(task_id)
        sql = f"UPDATE user_tasks SET {', '.join(updates)} WHERE id = ?"

        with self.db.transaction() as conn:
            conn.execute(sql, tuple(params))

        return self.get_task(task_id)

    def complete_task(self, task_id: int) -> Optional[TaskItem]:
        """Mark task as completed."""
        return self.update_task(task_id, status=TaskStatus.COMPLETED.value)

    def delete_task(self, task_id: int) -> bool:
        """Permanently delete a task."""
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM user_tasks WHERE id = ?", (task_id,))
            return cur.rowcount > 0

    # -------------------------------------------------------------------------
    # REMINDERS REPOSITORY & ATOMIC LEASES
    # -------------------------------------------------------------------------

    def add_reminder(
        self,
        title: str,
        remind_at: str,
        recurrence: str = RecurrenceType.NONE.value,
        priority: str = "normal",
    ) -> ReminderItem:
        """Create a scheduled reminder with duplicate detection."""
        if not title or not title.strip():
            raise ValueError("Reminder title cannot be empty.")

        clean_dt = DateTimeParser.parse(remind_at)
        target_iso = DateTimeParser.to_iso(clean_dt)
        now_dt = DateTimeParser.now_local()
        now_iso = DateTimeParser.to_iso(now_dt)

        clean_recurrence = recurrence.lower().strip()
        if clean_recurrence not in [r.value for r in RecurrenceType]:
            clean_recurrence = RecurrenceType.NONE.value

        # De-duplication check: identical title within 60 seconds
        dt_min = clean_dt - timedelta(seconds=60)
        dt_max = clean_dt + timedelta(seconds=60)
        iso_min = DateTimeParser.to_iso(dt_min)
        iso_max = DateTimeParser.to_iso(dt_max)

        existing = self.db.fetch_one(
            """
            SELECT id FROM reminders
            WHERE LOWER(title) = LOWER(?)
              AND remind_at BETWEEN ? AND ?
              AND completed = 0
              AND status NOT IN ('cancelled', 'expired')
            """,
            (title.strip(), iso_min, iso_max),
        )
        if existing:
            raise ValueError(
                f"Duplicate reminder detected: A reminder '{title}' is already scheduled "
                f"around that time (ID: {existing['id']})."
            )

        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO reminders (title, remind_at, created_at, completed, recurrence, priority, status)
                VALUES (?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    title.strip(),
                    target_iso,
                    now_iso,
                    clean_recurrence,
                    priority.lower().strip(),
                    ReminderStatus.PENDING.value,
                ),
            )
            reminder_id = cur.lastrowid

        return self.get_reminder(reminder_id)  # type: ignore[return-value]

    def get_reminder(self, reminder_id: int) -> Optional[ReminderItem]:
        """Retrieve a reminder by ID."""
        row = self.db.fetch_one(
            """
            SELECT id, title, remind_at, created_at, completed, recurrence, priority, status,
                   lease_until, claimed_by, dispatched_at, delivery_channels, dispatch_attempts, last_error
            FROM reminders WHERE id = ?
            """,
            (reminder_id,),
        )
        if not row:
            return None
        return ReminderItem(
            id=row["id"],
            title=row["title"],
            remind_at=row["remind_at"],
            created_at=row["created_at"],
            completed=int(row["completed"]),
            recurrence=row["recurrence"] or RecurrenceType.NONE.value,
            priority=row["priority"] or "normal",
            status=row["status"] or ReminderStatus.PENDING.value,
            lease_until=row["lease_until"],
            claimed_by=row["claimed_by"],
            dispatched_at=row["dispatched_at"],
            delivery_channels=row["delivery_channels"] or "[]",
            dispatch_attempts=int(row["dispatch_attempts"] or 0),
            last_error=row["last_error"],
        )

    def list_reminders(
        self,
        status: Optional[str] = None,
        include_completed: bool = False,
        limit: int = 50,
    ) -> List[ReminderItem]:
        """List scheduled reminders."""
        query = (
            "SELECT id, title, remind_at, created_at, completed, recurrence, priority, status, "
            "lease_until, claimed_by, dispatched_at, delivery_channels, dispatch_attempts, last_error "
            "FROM reminders WHERE 1=1"
        )
        params: list[Any] = []

        if not include_completed:
            query += " AND completed = 0 AND status NOT IN ('cancelled', 'expired')"

        if status:
            query += " AND status = ?"
            params.append(status.lower().strip())

        query += " ORDER BY remind_at ASC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(query, tuple(params))
        return [
            ReminderItem(
                id=r["id"],
                title=r["title"],
                remind_at=r["remind_at"],
                created_at=r["created_at"],
                completed=int(r["completed"]),
                recurrence=r["recurrence"] or RecurrenceType.NONE.value,
                priority=r["priority"] or "normal",
                status=r["status"] or ReminderStatus.PENDING.value,
                lease_until=r["lease_until"],
                claimed_by=r["claimed_by"],
                dispatched_at=r["dispatched_at"],
                delivery_channels=r["delivery_channels"] or "[]",
                dispatch_attempts=int(r["dispatch_attempts"] or 0),
                last_error=r["last_error"],
            )
            for r in rows
        ]

    def reschedule_reminder(self, reminder_id: int, new_remind_at: str) -> Optional[ReminderItem]:
        """Reschedule an existing reminder to a new datetime."""
        target_dt = DateTimeParser.parse(new_remind_at)
        target_iso = DateTimeParser.to_iso(target_dt)

        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE reminders
                SET remind_at = ?, status = 'pending', completed = 0, lease_until = NULL, claimed_by = NULL
                WHERE id = ?
                """,
                (target_iso, reminder_id),
            )
            if cur.rowcount == 0:
                return None

        return self.get_reminder(reminder_id)

    def cancel_reminder(self, reminder_id: int) -> Optional[ReminderItem]:
        """Cancel a reminder."""
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE reminders SET status = 'cancelled', lease_until = NULL, claimed_by = NULL WHERE id = ?",
                (reminder_id,),
            )
            if cur.rowcount == 0:
                return None

        return self.get_reminder(reminder_id)

    def complete_reminder(self, reminder_id: int) -> Optional[ReminderItem]:
        """Mark reminder completed."""
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE reminders SET completed = 1, status = 'completed', lease_until = NULL, claimed_by = NULL WHERE id = ?",
                (reminder_id,),
            )
            if cur.rowcount == 0:
                return None

        return self.get_reminder(reminder_id)

    def acknowledge_reminder(self, reminder_id: int) -> Optional[ReminderItem]:
        """Acknowledge a dispatched reminder."""
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE reminders SET status = 'acknowledged' WHERE id = ?",
                (reminder_id,),
            )
            if cur.rowcount == 0:
                return None

        return self.get_reminder(reminder_id)

    def delete_reminder(self, reminder_id: int) -> bool:
        """Permanently delete a reminder."""
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            return cur.rowcount > 0

    def claim_due_reminders(
        self,
        worker_id: str,
        now_iso: str,
        lease_seconds: float = 30.0,
        limit: int = 10,
    ) -> List[ReminderItem]:
        """Atomically acquire dispatch leases on due or recovered-stale reminders.

        Concurrency & Crash Safety:
        Uses an atomic UPDATE with WHERE condition ensuring only one worker claims each item.
        """
        now_dt = DateTimeParser.from_iso(now_iso)
        lease_expiry = DateTimeParser.to_iso(now_dt + timedelta(seconds=lease_seconds))

        claimed_items: list[ReminderItem] = []

        with self.db.transaction() as conn:
            cur = conn.cursor()
            # Select candidate IDs
            cur.execute(
                """
                SELECT id FROM reminders
                WHERE completed = 0
                  AND (
                    (status IN ('pending', 'due', 'missed') AND remind_at <= ?)
                    OR
                    (status = 'dispatching' AND lease_until IS NOT NULL AND lease_until < ?)
                  )
                ORDER BY remind_at ASC
                LIMIT ?
                """,
                (now_iso, now_iso, limit),
            )
            candidate_rows = cur.fetchall()

            for row in candidate_rows:
                cand_id = row[0]
                cur.execute(
                    """
                    UPDATE reminders
                    SET status = 'dispatching',
                        lease_until = ?,
                        claimed_by = ?
                    WHERE id = ?
                      AND (
                        status IN ('pending', 'due', 'missed')
                        OR (status = 'dispatching' AND lease_until < ?)
                      )
                    """,
                    (lease_expiry, worker_id, cand_id, now_iso),
                )
                if cur.rowcount > 0:
                    item = self.get_reminder(cand_id)
                    if item:
                        claimed_items.append(item)

        return claimed_items

    def mark_dispatched(
        self,
        reminder_id: int,
        worker_id: str,
        channels: Optional[list[str]] = None,
        now_iso: Optional[str] = None,
    ) -> bool:
        """Record successful dispatch and advance recurring schedule if applicable."""
        cur_iso = now_iso or DateTimeParser.to_iso(DateTimeParser.now_local())
        cur_dt = DateTimeParser.from_iso(cur_iso)
        channels_json = json.dumps(channels or ["voice", "ui"])

        item = self.get_reminder(reminder_id)
        if not item:
            return False

        with self.db.transaction() as conn:
            cur = conn.cursor()
            if item.recurrence and item.recurrence != RecurrenceType.NONE.value:
                # Recurring reminder: calculate next occurrence
                remind_dt = DateTimeParser.from_iso(item.remind_at)
                next_dt = RecurrenceEngine.calculate_next_occurrence(remind_dt, item.recurrence)
                # If calculated next is still in the past, collapse backlog to future
                if next_dt and next_dt <= cur_dt:
                    collapsed_dt, _ = RecurrenceEngine.collapse_missed_recurrences(next_dt, item.recurrence, cur_dt)
                    next_dt = collapsed_dt or (cur_dt + timedelta(days=1))

                next_iso = DateTimeParser.to_iso(next_dt) if next_dt else cur_iso

                cur.execute(
                    """
                    UPDATE reminders
                    SET status = 'pending',
                        remind_at = ?,
                        dispatched_at = ?,
                        delivery_channels = ?,
                        lease_until = NULL,
                        claimed_by = NULL,
                        dispatch_attempts = 0,
                        last_error = NULL
                    WHERE id = ? AND claimed_by = ?
                    """,
                    (next_iso, cur_iso, channels_json, reminder_id, worker_id),
                )
            else:
                # One-time reminder
                cur.execute(
                    """
                    UPDATE reminders
                    SET status = 'dispatched',
                        completed = 1,
                        dispatched_at = ?,
                        delivery_channels = ?,
                        lease_until = NULL,
                        claimed_by = NULL,
                        last_error = NULL
                    WHERE id = ? AND claimed_by = ?
                    """,
                    (cur_iso, channels_json, reminder_id, worker_id),
                )
            return cur.rowcount > 0

    def mark_dispatch_failed(
        self,
        reminder_id: int,
        worker_id: str,
        error: Optional[str] = None,
        max_retries: int = 3,
        now_iso: Optional[str] = None,
    ) -> bool:
        """Handle dispatch delivery failure with exponential backoff or terminal failure."""
        cur_iso = now_iso or DateTimeParser.to_iso(DateTimeParser.now_local())
        cur_dt = DateTimeParser.from_iso(cur_iso)

        item = self.get_reminder(reminder_id)
        if not item:
            return False

        attempts = item.dispatch_attempts + 1

        with self.db.transaction() as conn:
            cur = conn.cursor()
            if attempts < max_retries:
                # Retry with backoff (30s * attempts)
                backoff_dt = cur_dt + timedelta(seconds=30.0 * attempts)
                backoff_iso = DateTimeParser.to_iso(backoff_dt)
                cur.execute(
                    """
                    UPDATE reminders
                    SET status = 'pending',
                        remind_at = ?,
                        dispatch_attempts = ?,
                        last_error = ?,
                        lease_until = NULL,
                        claimed_by = NULL
                    WHERE id = ? AND claimed_by = ?
                    """,
                    (backoff_iso, attempts, error, reminder_id, worker_id),
                )
            else:
                # Terminal failure
                cur.execute(
                    """
                    UPDATE reminders
                    SET status = 'dispatch_failed',
                        dispatch_attempts = ?,
                        last_error = ?,
                        lease_until = NULL,
                        claimed_by = NULL
                    WHERE id = ? AND claimed_by = ?
                    """,
                    (attempts, error, reminder_id, worker_id),
                )
            return cur.rowcount > 0

    def recover_startup_reminders(
        self,
        now_iso: str,
        grace_hours: float = 24.0,
    ) -> dict[str, int]:
        """Perform restart recovery for overdue reminders and stale in-progress leases."""
        now_dt = DateTimeParser.from_iso(now_iso)
        cutoff_dt = now_dt - timedelta(hours=grace_hours)
        cutoff_iso = DateTimeParser.to_iso(cutoff_dt)

        stats = {"missed": 0, "expired": 0, "stale_leases": 0}

        with self.db.transaction() as conn:
            cur = conn.cursor()

            # 1. Recover stale leases
            cur.execute(
                """
                UPDATE reminders
                SET status = 'pending', lease_until = NULL, claimed_by = NULL
                WHERE status = 'dispatching' AND lease_until < ?
                """,
                (now_iso,),
            )
            stats["stale_leases"] = cur.rowcount

            # 2. Mark elapsed pending as missed (within grace window)
            cur.execute(
                """
                UPDATE reminders
                SET status = 'missed'
                WHERE status = 'pending' AND completed = 0
                  AND remind_at < ? AND remind_at >= ?
                """,
                (now_iso, cutoff_iso),
            )
            stats["missed"] = cur.rowcount

            # 3. Mark elapsed pending older than grace window as expired
            cur.execute(
                """
                UPDATE reminders
                SET status = 'expired'
                WHERE status = 'pending' AND completed = 0
                  AND remind_at < ?
                """,
                (cutoff_iso,),
            )
            stats["expired"] = cur.rowcount

        return stats

    # -------------------------------------------------------------------------
    # NOTES REPOSITORY & FULL-TEXT SEARCH (FTS5)
    # -------------------------------------------------------------------------

    def save_note(self, title: str, content: str) -> NoteItem:
        """Save a new note and update FTS5 search index."""
        if not title or not title.strip():
            raise ValueError("Note title cannot be empty.")

        now_iso = DateTimeParser.to_iso(DateTimeParser.now_local())

        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO notes (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (title.strip(), content.strip(), now_iso, now_iso),
            )
            note_id = cur.lastrowid
            try:
                cur.execute(
                    "INSERT INTO notes_fts (note_id, title, content) VALUES (?, ?, ?)",
                    (note_id, title.strip(), content.strip()),
                )
            except Exception as fts_err:
                logger.warning("FTS index insertion failed for note %s: %s", note_id, fts_err)

        return self.get_note(note_id)  # type: ignore[return-value]

    def get_note(self, note_id: int) -> Optional[NoteItem]:
        """Retrieve a note by ID."""
        row = self.db.fetch_one(
            "SELECT id, title, content, created_at, updated_at FROM notes WHERE id = ?",
            (note_id,),
        )
        if not row:
            return None
        return NoteItem(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_notes(self, limit: int = 50) -> List[NoteItem]:
        """List user notes ordered by newest updated first."""
        rows = self.db.fetch_all(
            "SELECT id, title, content, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [
            NoteItem(
                id=r["id"],
                title=r["title"],
                content=r["content"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def search_notes(self, query: str, limit: int = 20) -> List[NoteItem]:
        """Search notes using SQLite FTS5 with fallback to LIKE pattern matching."""
        if not query or not query.strip():
            return self.list_notes(limit=limit)

        clean_q = query.strip()
        # Attempt FTS5 MATCH
        try:
            # Escape problematic FTS5 characters or use quoted terms
            fts_term = '"' + clean_q.replace('"', '""') + '"'
            rows = self.db.fetch_all(
                """
                SELECT n.id, n.title, n.content, n.created_at, n.updated_at
                FROM notes n
                JOIN notes_fts f ON n.id = f.note_id
                WHERE notes_fts MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (fts_term, limit),
            )
            if rows:
                return [
                    NoteItem(
                        id=r["id"],
                        title=r["title"],
                        content=r["content"],
                        created_at=r["created_at"],
                        updated_at=r["updated_at"],
                    )
                    for r in rows
                ]
        except Exception as fts_err:
            logger.debug("FTS5 query failed, falling back to LIKE: %s", fts_err)

        # Fallback to standard LIKE
        like_pattern = f"%{clean_q}%"
        rows = self.db.fetch_all(
            """
            SELECT id, title, content, created_at, updated_at
            FROM notes
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (like_pattern, like_pattern, limit),
        )
        return [
            NoteItem(
                id=r["id"],
                title=r["title"],
                content=r["content"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def delete_note(self, note_id: int) -> bool:
        """Permanently delete a note and remove it from FTS index."""
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            del_count = cur.rowcount
            try:
                cur.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
            except Exception:
                pass
            return del_count > 0

    # -------------------------------------------------------------------------
    # DAILY PLAN AGGREGATION
    # -------------------------------------------------------------------------

    def get_daily_items(
        self, target_date_iso: Optional[str] = None
    ) -> Tuple[List[TaskItem], List[ReminderItem], List[TaskItem], List[ReminderItem]]:
        """Return (tasks_due_today, reminders_due_today, overdue_tasks, overdue_reminders)."""
        ref_dt = (
            DateTimeParser.from_iso(target_date_iso)
            if target_date_iso
            else DateTimeParser.now_local()
        )
        start_of_day = datetime(ref_dt.year, ref_dt.month, ref_dt.day, 0, 0, 0, tzinfo=ref_dt.tzinfo)
        end_of_day = datetime(ref_dt.year, ref_dt.month, ref_dt.day, 23, 59, 59, tzinfo=ref_dt.tzinfo)

        start_iso = DateTimeParser.to_iso(start_of_day)
        end_iso = DateTimeParser.to_iso(end_of_day)
        now_iso = DateTimeParser.to_iso(ref_dt)

        # Tasks due today
        all_tasks = self.list_tasks(limit=200)
        tasks_due: list[TaskItem] = []
        overdue_tasks: list[TaskItem] = []

        for t in all_tasks:
            if t.status in (TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value):
                continue
            if t.due_date:
                if start_iso <= t.due_date <= end_iso:
                    tasks_due.append(t)
                elif t.due_date < start_iso:
                    overdue_tasks.append(t)

        # Reminders due today
        all_reminders = self.list_reminders(include_completed=False, limit=200)
        reminders_due: list[ReminderItem] = []
        overdue_reminders: list[ReminderItem] = []

        for r in all_reminders:
            if start_iso <= r.remind_at <= end_iso:
                reminders_due.append(r)
            elif r.remind_at < start_iso:
                overdue_reminders.append(r)

        return tasks_due, reminders_due, overdue_tasks, overdue_reminders
