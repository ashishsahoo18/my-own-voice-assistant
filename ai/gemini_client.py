"""AI and offline Q&A answer generation removed per specification.
All normal questions are now routed directly to web search.
"""

from __future__ import annotations

from typing import Optional
from collections.abc import Generator

OFFLINE_RESPONSE = (
    "AI conversation answering has been disabled. "
    "All normal questions are searched directly on Google."
)


class GeminiClient:
    """Stub client - AI Q&A answering is disabled."""

    def __init__(self) -> None:
        self.api_key = ""
        self.client = None
        self.quota_exhausted = True

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        """AI Q&A answering disabled; returns search notice."""
        return OFFLINE_RESPONSE

    def stream(self, prompt: str, history: Optional[list[dict]] = None) -> Generator[str, None, None]:
        yield self.ask(prompt, history)


client = GeminiClient()


def generate_ai_response(prompt: str, history: list[dict[str, str]] | None = None) -> str:
    """Disabled AI response generator."""
    return client.ask(prompt, history)


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Disabled AI response wrapper."""
    return client.ask(prompt, history)


def stream_ai_response(
    prompt: str,
    history: Optional[list[dict]] = None,
) -> Generator[str, None, None]:
    yield from client.stream(prompt, history)
