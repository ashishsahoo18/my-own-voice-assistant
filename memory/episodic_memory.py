"""Episodic memory manager for multi-session conversation history."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from memory.unified_db import UnifiedDatabase, get_unified_db

logger = logging.getLogger("oliver.memory.episodic")


class EpisodicMemory:
    """Manages conversational session history and turn retrieval across sessions."""

    def __init__(self, db: Optional[UnifiedDatabase] = None) -> None:
        self.db = db or get_unified_db()

    def create_or_get_session(self, session_id: str, title: str = "New Conversation") -> str:
        """Ensure session exists in database."""
        now = datetime.now().isoformat()
        self.db.execute(
            """
            INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, title, now, now),
        )
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Persist a dialogue turn in the active session."""
        now = datetime.now().isoformat()
        self.create_or_get_session(session_id)

        meta_str = json.dumps(metadata or {})
        tokens_estimate = len(content.split())

        cur = self.db.execute(
            """
            INSERT INTO messages (session_id, role, content, created_at, tokens_estimate, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, role, content, now, tokens_estimate, meta_str),
        )

        # Update session timestamp
        self.db.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        return cur.lastrowid or 0

    def get_recent_messages(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Retrieve the most recent messages for a session in chronological order."""
        rows = self.db.fetch_all(
            """
            SELECT id, role, content, created_at, metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
        # Reverse to return chronological order
        result = []
        for r in reversed(rows):
            meta = {}
            try:
                meta = json.loads(r["metadata"] or "{}")
            except Exception:
                pass
            result.append({
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
                "metadata": meta,
            })
        return result

    def get_session_messages(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Alias for get_recent_messages."""
        return self.get_recent_messages(session_id, limit=limit)

    def get_formatted_context(self, session_id: str, limit: int = 10) -> str:
        """Format recent dialogue turns for system prompt context injection."""
        messages = self.get_recent_messages(session_id, limit)
        if not messages:
            return ""

        formatted_lines = []
        for m in messages:
            speaker = "User" if m["role"] == "user" else "Assistant"
            formatted_lines.append(f"{speaker}: {m['content']}")

        return "\n".join(formatted_lines)

    get_context_prompt = get_formatted_context

    def clear_session(self, session_id: str) -> None:
        """Delete all messages and session context for a specific session."""
        self.db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        self.db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        """List stored conversation sessions."""
        rows = self.db.fetch_all(
            """
            SELECT s.session_id, s.title, s.created_at, s.updated_at, COUNT(m.id) as message_count
            FROM sessions s
            LEFT JOIN messages m ON s.session_id = m.session_id
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]
