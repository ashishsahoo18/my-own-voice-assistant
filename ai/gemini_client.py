"""Gemini/offline AI client for AYRA AI."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OFFLINE_RESPONSE = (
    "I am running in offline mode. I can still help with opening apps, "
    "YouTube search, Google search, WhatsApp, reminders, notes, screenshots, "
    "files, folders, and basic calculations."
)


class GeminiClient:
    """Use Gemini when available, otherwise use offline responses."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        self.client = None
        self.quota_exhausted = False

        if self.api_key and genai is not None and types is not None:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception:
                self.client = None

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        """Return Gemini response or offline fallback."""
        if not self.client or self.quota_exhausted:
            return self._offline_answer(prompt)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self._system_prompt(),
                    temperature=0.7,
                ),
            )
            text = getattr(response, "text", "")
            return text.strip() if text else self._offline_answer(prompt)
        except Exception as exc:
            if self._is_quota_error(exc):
                self.quota_exhausted = True
            return self._offline_answer(prompt)

    def stream(self, prompt: str, history: Optional[list[dict]] = None) -> Generator[str, None, None]:
        """Streaming-compatible fallback."""
        yield self.ask(prompt, history)

    def _is_quota_error(self, exc: Exception) -> bool:
        """Detect Gemini quota/rate-limit errors."""
        message = str(exc).lower()
        return (
            "429" in message
            or "resource_exhausted" in message
            or "quota" in message
            or "rate limit" in message
        )

    def _offline_answer(self, prompt: str) -> str:
        """Simple offline answers without API key or quota."""
        text = prompt.lower().strip()

        if "http" in text:
            return (
                "HTTP means HyperText Transfer Protocol. It is the protocol "
                "browsers and servers use to exchange web pages and data."
            )

        if "python" in text:
            return (
                "Python is a high-level programming language used for automation, "
                "web development, data analysis, AI, and scripting."
            )

        if "bfs" in text:
            return (
                "BFS means Breadth-First Search. It explores a graph level by level "
                "and usually uses a queue."
            )

        if "dfs" in text:
            return (
                "DFS means Depth-First Search. It explores deeply along one path "
                "before backtracking."
            )

        if "who are you" in text or "your name" in text:
            return "I am AYRA AI, your desktop assistant."

        if "what can you do" in text:
            return OFFLINE_RESPONSE

        return OFFLINE_RESPONSE

    def _system_prompt(self) -> str:
        return (
            "You are AYRA AI, Ashish's premium desktop assistant. "
            "Reply clearly, shortly, and helpfully. Understand Hinglish."
        )


client = GeminiClient()


def generate_ai_response(prompt: str, history: list[dict[str, str]] | None = None) -> str:
    """Generate an AI response."""
    return client.ask(prompt, history)


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Backward-compatible wrapper."""
    return client.ask(prompt, history)


def stream_ai_response(
    prompt: str,
    history: Optional[list[dict]] = None,
) -> Generator[str, None, None]:
    """Yield a streaming-compatible response."""
    yield from client.stream(prompt, history)