from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from database.database import AyraDatabase
from database.models import MemoryItem, Reminder, UserProfile


class MemoryManager:
    """Manage user profile, memories, reminders, notes, and settings."""

    def __init__(self, db: Optional[AyraDatabase] = None) -> None:
        self.db = db or AyraDatabase()
        self.logger = self.db.logger

    def save_memory(self, content: str, category: str = "general", importance: float = 0.5) -> MemoryItem:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO memory (category, content, importance, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (category, content, importance, now, now),
            )
            connection.commit()
            self.logger.info("Memory saved: %s", content)
            return MemoryItem(id=int(cursor.lastrowid), category=category, content=content, importance=importance)

    def load_memory(self, limit: int = 20) -> list[MemoryItem]:
        with self.db._connect() as connection:
            rows = connection.execute(
                "SELECT id, category, content, importance FROM memory ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [MemoryItem(id=int(row["id"]), category=row["category"], content=row["content"], importance=float(row["importance"])) for row in rows]

    def update_memory(self, memory_id: int, content: str, category: str = "general", importance: float = 0.5) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db._connect() as connection:
            connection.execute(
                "UPDATE memory SET category = ?, content = ?, importance = ?, updated_at = ? WHERE id = ?",
                (category, content, importance, now, memory_id),
            )
            connection.commit()

    def delete_memory(self, memory_id: int) -> None:
        with self.db._connect() as connection:
            connection.execute("DELETE FROM memory WHERE id = ?", (memory_id,))
            connection.commit()

    def search_memory(self, query: str) -> list[MemoryItem]:
        with self.db._connect() as connection:
            rows = connection.execute(
                "SELECT id, category, content, importance FROM memory WHERE content LIKE ? ORDER BY importance DESC",
                (f"%{query}%",),
            ).fetchall()
            return [MemoryItem(id=int(row["id"]), category=row["category"], content=row["content"], importance=float(row["importance"])) for row in rows]

    def summarize_memory(self) -> str:
        memories = self.load_memory(limit=10)
        if not memories:
            return "No long-term memory yet."
        return "\n".join(f"- {item.content}" for item in memories)

    def save_user_profile(self, profile: UserProfile) -> UserProfile:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db._connect() as connection:
            existing = connection.execute("SELECT id FROM users LIMIT 1").fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE users SET name = ?, nickname = ?, preferred_language = ?, theme = ?, voice_settings = ?,
                    city = ?, country = ?, time_zone = ?, birthday = ?, profession = ?, skills = ?, interests = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (profile.name, profile.nickname, profile.preferred_language, profile.theme, profile.voice_settings, profile.city, profile.country, profile.time_zone, profile.birthday, profile.profession, profile.skills, profile.interests, now, existing["id"]),
                )
                profile.id = int(existing["id"])
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO users (name, nickname, preferred_language, theme, voice_settings, city, country, time_zone,
                    birthday, profession, skills, interests, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (profile.name, profile.nickname, profile.preferred_language, profile.theme, profile.voice_settings, profile.city, profile.country, profile.time_zone, profile.birthday, profile.profession, profile.skills, profile.interests, now, now),
                )
                profile.id = int(cursor.lastrowid)
            connection.commit()
        return profile

    def get_user_profile(self) -> Optional[UserProfile]:
        with self.db._connect() as connection:
            row = connection.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return None
            return UserProfile(
                id=int(row["id"]),
                name=row["name"],
                nickname=row["nickname"],
                preferred_language=row["preferred_language"],
                theme=row["theme"],
                voice_settings=row["voice_settings"],
                city=row["city"],
                country=row["country"],
                time_zone=row["time_zone"],
                birthday=row["birthday"],
                profession=row["profession"],
                skills=row["skills"],
                interests=row["interests"],
            )

    def save_setting(self, key: str, value: Any) -> None:
        with self.db._connect() as connection:
            connection.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value) if not isinstance(value, str) else value),
            )
            connection.commit()

    def load_setting(self, key: str, default: Any = None) -> Any:
        with self.db._connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if not row:
                return default
            value = row["value"]
            try:
                return json.loads(value)
            except Exception:
                return value

    def add_reminder(self, message: str, remind_at: str) -> Reminder:
        with self.db._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO reminders (message, remind_at, created_at, is_done) VALUES (?, ?, ?, 0)",
                (message, remind_at, datetime.now().isoformat(timespec="seconds")),
            )
            connection.commit()
            return Reminder(id=int(cursor.lastrowid), message=message, remind_at=remind_at, is_done=0)

    def list_reminders(self) -> list[Reminder]:
        with self.db._connect() as connection:
            rows = connection.execute("SELECT id, message, remind_at, is_done FROM reminders ORDER BY remind_at ASC").fetchall()
            return [Reminder(id=int(row["id"]), message=row["message"], remind_at=row["remind_at"], is_done=int(row["is_done"])) for row in rows]

    def add_note(self, title: str, content: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.db._connect() as connection:
            connection.execute(
                "INSERT INTO notes (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (title, content, now, now),
            )
            connection.commit()

    def search_notes(self, query: str) -> list[dict[str, Any]]:
        with self.db._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, content, created_at FROM notes WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
            return [{"id": int(row["id"]), "title": row["title"], "content": row["content"], "created_at": row["created_at"]} for row in rows]
