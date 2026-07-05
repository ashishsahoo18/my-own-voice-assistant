from __future__ import annotations

from typing import List, Dict


class ConversationMemory:
    """In-memory conversation history for the current session."""

    def __init__(self) -> None:
        self.history: List[Dict[str, str]] = []

    def add_user_message(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def add_assistant_message(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})

    def clear(self) -> None:
        self.history.clear()

    def snapshot(self) -> List[Dict[str, str]]:
        return list(self.history)
