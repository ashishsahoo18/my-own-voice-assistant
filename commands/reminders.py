from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Reminder:
    """A saved reminder item."""

    id: int
    title: str
    remind_at: str
    created_at: str
    completed: bool


class ReminderCommands:
    """Create, list, and complete reminders using SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.db_path = Path(db_path) if db_path else project_root / "database" / "ayra_memory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _initialize_database(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.commit()

    def add_reminder(self, title: str, remind_at: Optional[str] = None) -> str:
        """Save a reminder."""
        clean_title = title.strip()
        if not clean_title:
            return "Please tell me what to remind you about."

        reminder_time = remind_at.strip() if remind_at else datetime.now().isoformat(timespec="seconds")
        created_at = datetime.now().isoformat(timespec="seconds")

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO reminders (title, remind_at, created_at, completed)
                VALUES (?, ?, ?, 0)
                """,
                (clean_title, reminder_time, created_at),
            )
            connection.commit()

        return f"Reminder saved: {clean_title}"

    def list_reminders(self, include_completed: bool = False) -> str:
        """Return saved reminders as readable text."""
        query = """
            SELECT id, title, remind_at, created_at, completed
            FROM reminders
        """
        params: tuple[object, ...] = ()

        if not include_completed:
            query += " WHERE completed = 0"

        query += " ORDER BY remind_at ASC, id ASC"

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()

        if not rows:
            return "No reminders found."

        reminders = [self._row_to_reminder(row) for row in rows]
        lines = []
        for reminder in reminders:
            status = "done" if reminder.completed else "pending"
            lines.append(f"{reminder.id}. {reminder.title} at {reminder.remind_at} [{status}]")

        return "\n".join(lines)

    def complete_reminder(self, reminder_id: int) -> str:
        """Mark a reminder as completed."""
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                "UPDATE reminders SET completed = 1 WHERE id = ?",
                (reminder_id,),
            )
            connection.commit()

        if cursor.rowcount == 0:
            return f"Reminder not found: {reminder_id}"

        return "Reminder completed."

    def delete_reminder(self, reminder_id: int) -> str:
        """Delete a reminder by id."""
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                "DELETE FROM reminders WHERE id = ?",
                (reminder_id,),
            )
            connection.commit()

        if cursor.rowcount == 0:
            return f"Reminder not found: {reminder_id}"

        return "Reminder deleted."

    def _row_to_reminder(self, row: sqlite3.Row) -> Reminder:
        return Reminder(
            id=int(row["id"]),
            title=str(row["title"]),
            remind_at=str(row["remind_at"]),
            created_at=str(row["created_at"]),
            completed=bool(row["completed"]),
        )