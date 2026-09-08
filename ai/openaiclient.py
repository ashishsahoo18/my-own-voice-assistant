"""AI answer generation disabled per specification."""

from __future__ import annotations

from typing import Optional


class GeminiClient:
    """Stub client - AI conversation answering disabled."""

    def __init__(self) -> None:
        self.api_key = ""

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        return "AI conversation answering has been disabled."


client = GeminiClient()


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    return client.ask(prompt=prompt, history=history)