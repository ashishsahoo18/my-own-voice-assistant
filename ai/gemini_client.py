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
        self.model = self._resolve_model_name()
        self.client = None
        self.quota_exhausted = False

        if self.api_key and genai is not None and types is not None:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception:
                self.client = None

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        """Return Gemini response or offline fallback."""
        self._last_history = history or []
        if not self.client or self.quota_exhausted:
            return self._offline_answer(prompt)

        trimmed_history = self._trim_history(history)
        contents: list[str] = [item.get("content", "") for item in trimmed_history if item.get("content")]
        contents.append(prompt)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
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
        status = getattr(exc, "status_code", None)
        return (
            "429" in message
            or "resource_exhausted" in message
            or "quota" in message
            or "rate limit" in message
            or status == 429
        )

    def _resolve_model_name(self) -> str:
        """Return a supported Gemini model name from environment or fallback."""
        configured = os.getenv("GEMINI_MODEL", "").strip()
        if configured:
            return configured
        return "gemini-1.5-flash"

    def _trim_history(self, history: Optional[list[dict]] = None, max_messages: int = 8) -> list[dict]:
        """Trim long conversation history to the most recent entries."""
        if not history:
            return []
        if len(history) <= max_messages:
            return history
        return history[-max_messages:]

    def _offline_answer(self, prompt: str) -> str:
        """Provide useful local answers when Gemini is unavailable or optional."""
        text = prompt.lower().strip()
        simple_request = any(phrase in text for phrase in ("simple words", "simply", "easy words"))

        if "machine learning" in text or (simple_request and "machine learning" in self._recent_history_text()):
            if simple_request:
                return (
                    "Machine learning is like teaching a computer with examples. "
                    "After seeing enough examples, it can recognize a pattern and make a useful guess."
                )
            return (
                "Machine learning is a part of AI where computers learn patterns from examples or data "
                "instead of receiving a separate rule for every situation. It powers things like recommendations, "
                "spam filters, and image recognition."
            )

        if "who created it" in text and "python" in self._recent_history_text():
            return "Python was created by Guido van Rossum and first released in 1991."

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

        if "c++" in text:
            return "C++ is a fast, general-purpose programming language often used for games, desktop software, systems, and performance-sensitive applications."

        if "array" in text:
            return "An array is a collection of values kept in order. You access each value using its position, called an index."

        if "loop" in text:
            return "A loop repeats a block of code. Use one when a task must happen for each item or until a condition changes."

        if "recursion" in text:
            return "Recursion is when a function solves a problem by calling itself on a smaller version of that problem, stopping at a base case."

        if "backend" in text:
            return "For backend development, start with Python or JavaScript, then learn HTTP, APIs, SQL and databases, authentication, Git, and a framework such as FastAPI, Django, Express, or NestJS. Build a small API as you learn."

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

        return (
            "I can help with that, but my optional online AI provider is unavailable right now. "
            "Ask for a definition, explanation, or step-by-step example and I will use local knowledge where possible."
        )

    def _recent_history_text(self) -> str:
        """Return recent conversation text for offline follow-up questions."""
        return " ".join(item.get("content", "").lower() for item in getattr(self, "_last_history", []))

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
