"""Gemini AI Client integration for ASHISH AI."""

from __future__ import annotations

from typing import Optional
from collections.abc import Generator
from ai.ai_service import AIService

OFFLINE_RESPONSE = "AI service is currently unavailable. Please set GEMINI_API_KEY in .env."


class GeminiClient:
    """Wrapper around AIService for backward compatibility."""

    def __init__(self) -> None:
        self.ai_service = AIService()

    @property
    def api_key(self) -> str:
        return self.ai_service.api_key

    @property
    def client(self) -> any:
        return self.ai_service.client

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        return self.ai_service.ask(prompt)

    def stream(self, prompt: str, history: Optional[list[dict]] = None) -> Generator[str, None, None]:
        yield self.ask(prompt, history)


client = GeminiClient()


def generate_ai_response(prompt: str, history: list[dict[str, str]] | None = None) -> str:
    return client.ask(prompt, history)


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    return client.ask(prompt, history)


def stream_ai_response(
    prompt: str,
    history: Optional[list[dict]] = None,
) -> Generator[str, None, None]:
    yield from client.stream(prompt, history)
