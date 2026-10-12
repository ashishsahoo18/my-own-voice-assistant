"""Unified Hybrid Memory Engine for OLIVER 2.0.

Integrates:
1. Working Memory (active conversation state & reference resolution)
2. Episodic Memory (multi-session dialogue history)
3. Semantic Memory (long-term facts, preferences, knowledge with privacy validation)

Exposes explicit user memory controls:
- "What do you remember?"
- "Forget this memory / Forget [x]"
- "Clear conversation / session memory"
- "Memory status / settings"
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from memory.episodic_memory import EpisodicMemory
from memory.privacy import MemoryPrivacyFilter
from memory.semantic_memory import SemanticMemory
from memory.unified_db import UnifiedDatabase, get_unified_db
from memory.working_memory import WorkingMemory

logger = logging.getLogger("oliver.memory.manager")


class HybridMemoryEngine:
    """Coordinator of Working, Episodic, and Semantic memory tiers."""

    def __init__(
        self,
        db: Optional[UnifiedDatabase] = None,
        privacy_filter: Optional[MemoryPrivacyFilter] = None,
    ) -> None:
        self.db = db or get_unified_db()
        self.privacy_filter = privacy_filter or MemoryPrivacyFilter()
        self.working = WorkingMemory(self.db)
        self.episodic = EpisodicMemory(self.db)
        self.semantic = SemanticMemory(self.db, self.privacy_filter)

    # --- Core Memory Operations ---

    def remember(
        self,
        content: str,
        category: str = "fact",
        importance: float = 0.7,
        key: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Explicitly learn and persist a fact or preference into long-term memory."""
        success, msg, _ = self.semantic.add_memory(
            content=content,
            category=category,
            key=key,
            importance=importance,
        )
        return success, msg

    def recall(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve memories relevant to the query."""
        results = self.semantic.search(query=query, limit=limit)
        return results

    def track_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        entities: Optional[list[tuple[str, str]]] = None,
    ) -> None:
        """Record dialogue turn into episodic memory and update working memory."""
        self.episodic.add_message(session_id, "user", user_message)
        self.episodic.add_message(session_id, "assistant", assistant_response)

        # Track entities in working memory
        if entities:
            for etype, evalue in entities:
                self.working.track_entity(session_id, etype, evalue)

    def set_candidates(self, session_id: str, candidates: list[str]) -> None:
        """Set ordered candidates in working memory for ordinal resolution."""
        self.working.set_candidates(session_id, candidates)

    def resolve_reference(self, text: str, session_id: str) -> tuple[str, Optional[str]]:
        """Resolve pronouns ('it', 'that one') and ordinals ('the second one') in text."""
        return self.working.resolve_reference(text, session_id)

    # --- Explicit Memory Controls ---

    def what_do_you_remember(self) -> str:
        """Return a user-friendly overview of everything OLIVER currently remembers."""
        memories = self.semantic.get_all(limit=100)
        if not memories:
            return "I do not currently have any stored personal memories or preferences."

        categories: dict[str, list[str]] = {}
        for m in memories:
            cat = m["category"].capitalize()
            categories.setdefault(cat, []).append(f"• [ID {m['id']}] {m['content']}")

        sections = []
        for cat, items in sorted(categories.items()):
            sections.append(f"### {cat}\n" + "\n".join(items))

        return "Here is what I remember about you:\n\n" + "\n\n".join(sections)

    def forget(self, target: str | int) -> str:
        """Delete memories by specific ID or matching text phrase."""
        # Try parsing as integer ID
        if isinstance(target, int) or (isinstance(target, str) and target.strip().isdigit()):
            mem_id = int(target)
            if self.semantic.delete_memory(mem_id):
                return f"Memory with ID {mem_id} has been forgotten."
            return f"No memory found with ID {mem_id}."

        target_str = str(target).strip()
        if not target_str or target_str.lower() in ("this memory", "recent memory", "last memory", "it"):
            all_mems = self.semantic.get_all(limit=1)
            if all_mems:
                recent_id = all_mems[0]["id"]
                recent_content = all_mems[0]["content"]
                self.semantic.delete_memory(recent_id)
                return f"Forgotten most recent memory: '{recent_content}' (ID {recent_id})."
            return "No stored memories found to forget."

        # Clean phrases like "forget that I like pizza" -> "I like pizza"
        for prefix in ("forget that ", "forget about ", "forget "):
            if target_str.lower().startswith(prefix):
                target_str = target_str[len(prefix):].strip()

        count = self.semantic.delete_by_content(target_str)
        if count > 0:
            return f"Removed {count} memory record(s) matching '{target_str}'."
        return f"No matching memories found for '{target_str}'."

    def clear_session_memory(self, session_id: str) -> str:
        """Clear active working memory and episodic history for a specific session."""
        self.working.clear(session_id)
        self.episodic.clear_session(session_id)
        return f"Cleared working and conversation memory for session '{session_id}'."

    def status(self) -> dict[str, Any]:
        """Return operational statistics across all memory tiers."""
        total_memories = self.semantic.count()
        sessions = self.episodic.list_sessions(limit=100)
        total_sessions = len(sessions)
        total_messages = sum(s.get("message_count", 0) for s in sessions)

        return {
            "database_path": str(self.db.db_path),
            "journal_mode": "WAL",
            "total_semantic_memories": total_memories,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
        }


_global_memory_engine: Optional[HybridMemoryEngine] = None


def get_memory_engine() -> HybridMemoryEngine:
    """Return singleton instance of the HybridMemoryEngine."""
    global _global_memory_engine
    if _global_memory_engine is None:
        _global_memory_engine = HybridMemoryEngine()
    return _global_memory_engine
