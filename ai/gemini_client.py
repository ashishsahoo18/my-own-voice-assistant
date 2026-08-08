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
        # Track quota exhaustion to avoid repeated retries on 429
        self.quota_exhausted: bool = False
        self.quota_reset_ts: float | None = None

        if self.api_key and genai is not None:
            self.client = genai.Client(api_key=self.api_key)

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        """Return Gemini response or offline fallback."""
        # If the client is not configured, fall back immediately
        if not self.client:
            return self._offline_answer(prompt)

        # If we previously detected a quota exhaustion, avoid retrying until reset
        import time

        if self.quota_exhausted:
            if self.quota_reset_ts and time.time() < self.quota_reset_ts:
                raise GeminiQuotaExceeded("Gemini quota exhausted until reset")
            # quota_reset_ts passed -> clear flag and attempt again
            self.quota_exhausted = False
            self.quota_reset_ts = None

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
        except Exception as exc:
            # Detect quota/exhausted errors (HTTP 429 / RESOURCE_EXHAUSTED)
            from google.genai import errors as _genai_errors
            import traceback
            print("AYRA AI ERROR:", repr(exc))
            traceback.print_exc()

            # Many genai client errors expose status/details in the exception
            try:
                # genai ClientError exposes status_code and response_json
                status_code = getattr(exc, "status_code", None)
                resp = getattr(exc, "response_json", None)
            except Exception:
                status_code = None
                resp = None

            # Check heuristics for quota exhausted
            is_quota = False
            if status_code == 429:
                is_quota = True
            if resp and isinstance(resp, dict):
                # Look for RESOURCE_EXHAUSTED in status or message
                err = resp.get("error") or {}
                msg = err.get("message", "")
                if "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                    is_quota = True
                # Try to parse retry info seconds
                for d in err.get("details", []):
                    if isinstance(d, dict) and d.get("@type", "").endswith("RetryInfo"):
                        # may include retryDelay like '54s' or similar
                        for v in d.values():
                            if isinstance(v, str) and v.endswith("s") and v[:-1].isdigit():
                                try:
                                    import time

                                    self.quota_reset_ts = time.time() + int(v[:-1])
                                except Exception:
                                    pass
            # Fallback: check repr for RESOURCE_EXHAUSTED
            if not is_quota and "RESOURCE_EXHAUSTED" in repr(exc):
                is_quota = True

            if is_quota:
                # mark exhausted and avoid retrying until reset time
                import time

                self.quota_exhausted = True
                if self.quota_reset_ts is None:
                    # default to 60 seconds if unknown
                    self.quota_reset_ts = time.time() + 60
                # Raise a sentinel so caller can react specifically
                raise GeminiQuotaExceeded("Gemini API quota exhausted")

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


class GeminiQuotaExceeded(Exception):
    """Raised when Gemini returns an explicit quota/exhausted response (429)."""
    pass


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