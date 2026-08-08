"""Gemini/offline AI client for AYRA AI."""

from __future__ import annotations

import os
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

        if self.api_key and genai is not None:
            self.client = genai.Client(api_key=self.api_key)

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        """Return Gemini response or offline fallback."""
        if not self.client:
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
            return getattr(response, "text", "").strip() or self._offline_answer(prompt)
        except Exception:
            return self._offline_answer(prompt)

    def _offline_answer(self, prompt: str) -> str:
        """Simple offline answers without API key."""
        text = prompt.lower().strip()

        if "http" in text:
            return (
                "HTTP means HyperText Transfer Protocol. It is the rule system browsers "
                "and servers use to send web pages and data over the internet."
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


def stream_ai_response(prompt: str, history: Optional[list[dict]] = None):
    """Simple streaming-compatible wrapper."""
    yield client.ask(prompt, history)