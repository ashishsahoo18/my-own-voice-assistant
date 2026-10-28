"""Semantic long-term memory engine with privacy gating and importance ranking."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from memory.privacy import MemoryPrivacyFilter
from memory.unified_db import UnifiedDatabase, get_unified_db

logger = logging.getLogger("oliver.memory.semantic")


class SemanticMemory:
    """Manages long-term user facts, preferences, and knowledge with privacy enforcement."""

    def __init__(
        self,
        db: Optional[UnifiedDatabase] = None,
        privacy_filter: Optional[MemoryPrivacyFilter] = None,
    ) -> None:
        self.db = db or get_unified_db()
        self.privacy_filter = privacy_filter or MemoryPrivacyFilter()

    def add_memory(
        self,
        content: str,
        category: str = "general",
        key: Optional[str] = None,
        importance: float = 0.7,
    ) -> tuple[bool, str, Optional[int]]:
        """Add a new fact or preference to long-term memory after strict privacy validation.

        Returns:
            (success, explanation, memory_id)
        """
        clean_content = content.strip()
        if not clean_content:
            return False, "Cannot store empty content.", None

        # 1. Deterministic Privacy Filter
        is_safe, violation = self.privacy_filter.validate_for_storage(clean_content)
        if not is_safe:
            logger.warning("Memory store rejected by privacy filter: %s", violation)
            return False, f"Memory rejected: {violation}", None

        # 2. Store in unified database
        now = datetime.now().isoformat()
        clamped_importance = max(0.0, min(1.0, float(importance)))

        # If key is provided and already exists, update content and importance
        if key:
            existing = self.db.fetch_one("SELECT id FROM memories WHERE key = ?", (key,))
            if existing:
                self.db.execute(
                    """
                    UPDATE memories
                    SET content = ?, category = ?, importance = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (clean_content, category, clamped_importance, now, existing["id"]),
                )
                return True, f"Updated memory for key '{key}'.", existing["id"]

        cur = self.db.execute(
            """
            INSERT INTO memories (category, key, content, importance, created_at, updated_at, access_count)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (category, key, clean_content, clamped_importance, now, now),
        )
        mem_id = cur.lastrowid
        logger.info("Persisted long-term memory (id=%s, cat=%s, imp=%.2f)", mem_id, category, clamped_importance)
        return True, "Memory stored successfully.", mem_id

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search stored memories using keyword matching and importance scoring."""
        clean_query = query.strip()
        if not clean_query:
            return self.get_all(category=category, limit=limit)

        sql = """
            SELECT id, category, key, content, importance, created_at, updated_at, access_count
            FROM memories
            WHERE content LIKE ?
        """
        params: list[Any] = [f"%{clean_query}%"]

        if category:
            sql += " AND category = ?"
            params.append(category)

        sql += " ORDER BY importance DESC, access_count DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(sql, tuple(params))
        results = []

        now = datetime.now().isoformat()
        # Increment access count for recalled memories
        for r in rows:
            self.db.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                (now, r["id"]),
            )
            results.append(dict(r))

        return results

    def get_all(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve all stored memories ordered by importance."""
        if category:
            rows = self.db.fetch_all(
                """
                SELECT id, category, key, content, importance, created_at, updated_at, access_count
                FROM memories
                WHERE category = ?
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (category, limit),
            )
        else:
            rows = self.db.fetch_all(
                """
                SELECT id, category, key, content, importance, created_at, updated_at, access_count
                FROM memories
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [dict(r) for r in rows]

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory by its unique database ID."""
        cur = self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0

    def delete_by_content(self, text_pattern: str) -> int:
        """Delete memories matching a content phrase."""
        clean_pat = text_pattern.strip()
        if not clean_pat:
            return 0
        cur = self.db.execute("DELETE FROM memories WHERE content LIKE ?", (f"%{clean_pat}%",))
        return cur.rowcount

    def clear_all(self) -> int:
        """Delete all long-term memories."""
        cur = self.db.execute("DELETE FROM memories")
        return cur.rowcount

    def count(self) -> int:
        """Return total number of active memories."""
        row = self.db.fetch_one("SELECT COUNT(*) FROM memories")
        return row[0] if row else 0
