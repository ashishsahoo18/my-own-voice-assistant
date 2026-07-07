from __future__ import annotations

from ai.memory_manager import MemoryManager


class MemoryPromptBuilder:
    """Build a compact prompt with relevant long-term memories."""

    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory_manager = memory_manager

    def build(self, user_text: str) -> str:
        related = self.memory_manager.search_memory(user_text)
        if not related:
            related = self.memory_manager.load_memory(limit=5)
        if not related:
            return ""
        memory_lines = "\n".join(f"- {item.content}" for item in related[:5])
        return f"Relevant memory:\n{memory_lines}\n"
