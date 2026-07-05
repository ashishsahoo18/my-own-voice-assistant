import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional


class ChatStore:
    """Persist chat sessions and messages in a local SQLite database."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "ayra_chat.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._initialize_database()

    def _initialize_database(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL
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
            connection.commit()

    def get_or_create_session(self) -> int:
        with sqlite3.connect(self.db_path) as connection:
            latest = connection.execute(
                "SELECT id FROM chat_sessions ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if latest:
                return int(latest[0])

            created_at = datetime.now().isoformat(timespec="seconds")
            cursor = connection.execute(
                "INSERT INTO chat_sessions (started_at) VALUES (?)",
                (created_at,),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def save_message(self, session_id: int, role: str, content: str) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, datetime.now().isoformat(timespec="seconds")),
            )
            connection.commit()

    def session_has_messages(self, session_id: int) -> bool:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM chat_messages WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
            return row is not None

    def get_session_started_at(self, session_id: int) -> Optional[str]:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT started_at FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            return row[0] if row else None

    def load_all_sessions(self) -> List[Dict[str, object]]:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            sessions = connection.execute(
                "SELECT id, started_at FROM chat_sessions ORDER BY started_at ASC"
            ).fetchall()

            result: List[Dict[str, object]] = []
            for session in sessions:
                messages = connection.execute(
                    """
                    SELECT role, content, created_at
                    FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC, id ASC
                    """,
                    (session["id"],),
                ).fetchall()
                result.append(
                    {
                        "id": int(session["id"]),
                        "started_at": session["started_at"],
                        "messages": [
                            {
                                "role": message["role"],
                                "content": message["content"],
                                "created_at": message["created_at"],
                            }
                            for message in messages
                        ],
                    }
                )
            return result
