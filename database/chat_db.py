"""SQLite chat history storage for AYRA AI."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


SessionRecord = dict[str, Any]
MessageRecord = dict[str, str]


class ChatStore:
    """Persist chat sessions and messages in a local SQLite database."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        base_dir = Path(__file__).resolve().parent
        self.db_path = Path(db_path) if db_path else base_dir / "ayra_chat.db"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        """Create a SQLite connection with row access by column name."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        """Create or upgrade the chat database tables."""
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(id)
                )
                """
            )

            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(chat_sessions)").fetchall()
            }

            now = datetime.now().isoformat(timespec="seconds")

            if "title" not in columns:
                connection.execute(
                    "ALTER TABLE chat_sessions ADD COLUMN title TEXT NOT NULL DEFAULT 'New Chat'"
                )

            if "updated_at" not in columns:
                connection.execute(
                 "ALTER TABLE chat_sessions ADD COLUMN updated_at TEXT"
                )
                connection.execute(
                    "UPDATE chat_sessions SET updated_at = COALESCE(started_at, ?)",
                    (now,),
                )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
                ON chat_messages(session_id)
                """
            )

            connection.commit()

    def _migrate_existing_sessions(self, connection: sqlite3.Connection) -> None:
        """Add missing columns for older AYRA databases."""
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(chat_sessions)").fetchall()
        }

        if "title" not in columns:
            connection.execute("ALTER TABLE chat_sessions ADD COLUMN title TEXT")

        if "updated_at" not in columns:
            connection.execute("ALTER TABLE chat_sessions ADD COLUMN updated_at TEXT")
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = started_at
                WHERE updated_at IS NULL
                """
            )

    def get_or_create_session(self) -> int:
        """Return the latest session or create a new one."""
        with self._connect() as connection:
            latest = connection.execute(
                """
                SELECT id
                FROM chat_sessions
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

            if latest:
                return int(latest["id"])

            return self.create_session()

    def create_session(self, title: Optional[str] = None) -> int:
        """Create and return a new chat session ID."""
        now = self._now()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO chat_sessions (title, started_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (title, now, now),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def save_message(self, session_id: int, role: str, content: str) -> None:
        """Save a message in a chat session."""
        clean_role = role.strip().lower()
        clean_content = content.strip()

        if clean_role not in {"user", "assistant", "system"}:
            raise ValueError(f"Invalid chat role: {role}")

        if not clean_content:
            return

        now = self._now()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, clean_role, clean_content, now),
            )
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
            connection.commit()

    def session_has_messages(self, session_id: int) -> bool:
        """Return True when a session has at least one message."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM chat_messages
                WHERE session_id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            return row is not None

    def get_session_started_at(self, session_id: int) -> Optional[str]:
        """Return session start time."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT started_at
                FROM chat_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

            return str(row["started_at"]) if row else None

    def load_messages(self, session_id: int, limit: Optional[int] = None) -> list[MessageRecord]:
        """Load messages for a single session."""
        query = """
            SELECT role, content, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC, id ASC
        """
        params: tuple[object, ...] = (session_id,)

        if limit is not None:
            query += " LIMIT ?"
            params = (session_id, limit)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [
            {
                "role": str(row["role"]),
                "content": str(row["content"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def load_recent_messages(self, session_id: int, limit: int = 12) -> list[MessageRecord]:
        """Load recent messages for AI context."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        messages = [
            {
                "role": str(row["role"]),
                "content": str(row["content"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]
        return list(reversed(messages))

    def load_all_sessions(self) -> list[SessionRecord]:
        """Load every chat session with messages."""
        with self._connect() as connection:
            sessions = connection.execute(
                """
                SELECT id, title, started_at, updated_at
                FROM chat_sessions
                ORDER BY started_at ASC, id ASC
                """
            ).fetchall()

            result: list[SessionRecord] = []

            for session in sessions:
                session_id = int(session["id"])
                messages = self.load_messages(session_id)

                result.append(
                    {
                        "id": session_id,
                        "title": session["title"],
                        "started_at": session["started_at"],
                        "updated_at": session["updated_at"],
                        "messages": messages,
                    }
                )

            return result

    def clear_session(self, session_id: int) -> None:
        """Delete all messages from a session."""
        now = self._now()

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            connection.commit()

    def delete_session(self, session_id: int) -> None:
        """Delete a chat session and its messages."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM chat_sessions WHERE id = ?",
                (session_id,),
            )
            connection.commit()

    def _now(self) -> str:
        """Return current timestamp for database records."""
        return datetime.now().isoformat(timespec="seconds")