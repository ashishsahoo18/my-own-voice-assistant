"""Working memory and conversational reference resolution for OLIVER 2.0.

Maintains active conversational state (current session, recent entities, active folder/file)
and resolves conversational references like "it", "that one", "the second one".
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from memory.unified_db import UnifiedDatabase, get_unified_db

logger = logging.getLogger("oliver.memory.working")


class WorkingMemory:
    """Manages ephemeral working state and anaphora/reference resolution for active sessions."""

    ORDINAL_MAP = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
        "fourth": 3,
        "4th": 3,
        "fifth": 4,
        "5th": 4,
        "last": -1,
    }

    def __init__(self, db: Optional[UnifiedDatabase] = None) -> None:
        self.db = db or get_unified_db()

    def set(self, session_id: str, key: str, value: Any) -> None:
        """Store or update a key-value pair in active working memory for a session."""
        now = datetime.now().isoformat()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        self.db.execute(
            """
            INSERT INTO working_memory (session_id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (session_id, key, val_str, now),
        )

    def get(self, session_id: str, key: str, default: Any = None) -> Any:
        """Retrieve a key from working memory for a session."""
        row = self.db.fetch_one(
            "SELECT value FROM working_memory WHERE session_id = ? AND key = ?",
            (session_id, key),
        )
        if not row:
            return default

        val_str = row["value"]
        try:
            return json.loads(val_str)
        except Exception:
            return val_str

    def get_all(self, session_id: str) -> dict[str, Any]:
        """Return all working memory entries for a session."""
        rows = self.db.fetch_all(
            "SELECT key, value FROM working_memory WHERE session_id = ?",
            (session_id,),
        )
        result = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value"])
            except Exception:
                result[r["key"]] = r["value"]
        return result

    def clear(self, session_id: str) -> None:
        """Clear all working memory entries for a session."""
        self.db.execute("DELETE FROM working_memory WHERE session_id = ?", (session_id,))

    def track_entity(self, session_id: str, entity_type: str, entity_value: str) -> None:
        """Track recently mentioned entities (files, folders, targets, apps)."""
        clean_val = entity_value.strip()
        if not clean_val:
            return

        self.set(session_id, f"last_{entity_type}", clean_val)
        self.set(session_id, "last_entity", clean_val)

        # Update ordered candidates list
        candidates: list[str] = self.get(session_id, "recent_candidates", [])
        if clean_val in candidates:
            candidates.remove(clean_val)
        candidates.insert(0, clean_val)
        self.set(session_id, "recent_candidates", candidates[:10])

    def set_candidates(self, session_id: str, candidates: list[str]) -> None:
        """Explicitly set ordered candidates (e.g. from search results, listings, or options)."""
        clean = [c.strip() for c in candidates if c and c.strip()]
        self.set(session_id, "recent_candidates", clean[:10])
        if clean:
            self.set(session_id, "last_entity", clean[0])

    def resolve_reference(self, text: str, session_id: str) -> tuple[str, Optional[str]]:
        """Resolve pronouns and ordinals like 'it', 'that', 'the second one' in user input.

        Returns:
            (resolved_text, resolved_entity)
        """
        lowered = text.strip().lower()
        candidates: list[str] = self.get(session_id, "recent_candidates", [])

        # 1. Ordinal resolution: "the second one", "the first one", "the last one"
        ordinal_pattern = r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)(?:\s+one)?\b"
        match = re.search(ordinal_pattern, lowered)
        if match and candidates:
            ord_word = match.group(1)
            idx = self.ORDINAL_MAP.get(ord_word)
            if idx is not None and (idx == -1 or idx < len(candidates)):
                target = candidates[idx]
                resolved_text = re.sub(ordinal_pattern, f'"{target}"', text, count=1, flags=re.IGNORECASE)
                return resolved_text, target

        # 2. Pronoun resolution: "it", "that", "this", "that one", "there"
        pronoun_pattern = r"\b(it|that\s+one|that|this)\b"
        if re.search(pronoun_pattern, lowered) and candidates:
            last_entity = candidates[0]
            # Replace pronoun with quoted target
            resolved_text = re.sub(pronoun_pattern, f'"{last_entity}"', text, count=1, flags=re.IGNORECASE)
            return resolved_text, last_entity

        return text, None
