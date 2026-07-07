import os
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class GeminiClient:
    """Google Gemini client using the official GenAI Python SDK."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        self.system_prompt = (
            "You are Ayra, a friendly and capable AI assistant. "
            "Answer clearly, politely, and concisely. "
            "Support coding, productivity, web help, and general conversation."
        )
        self.client: Optional[genai.Client] = None

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file to enable AI replies.")

        if not self.client:
            raise RuntimeError("Gemini client is not configured.")

        try:
            contents = self._build_contents(prompt, history)
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=self.system_prompt),
            )
            return self._extract_text(response)
        except Exception as exc:
            traceback.print_exc()
            print(f"Actual Error: {exc}")
            if self._is_quota_error(exc):
                return (
                    "The AI service is currently rate-limited by Google. "
                    "Please wait a moment and try again."
                )
            raise

    def _is_quota_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            marker in message
            for marker in [
                "resource_exhausted",
                "quota exceeded",
                "quota",
                "rate limit",
                "too many requests",
                "429",
                "free_tier",
            ]
        )

    def _build_contents(self, prompt: str, history: Optional[list[dict]]) -> list[dict]:
        contents: list[dict] = []

        if history:
            for item in history:
                role = item.get("role", "user")
                text = item.get("content", "")
                if role == "assistant":
                    contents.append({"role": "model", "parts": [{"text": text}]})
                else:
                    contents.append({"role": "user", "parts": [{"text": text}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents

    def _extract_text(self, response: object) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        candidates = getattr(response, "candidates", None) or []
        if candidates:
            first = candidates[0]
            parts = getattr(first, "content", None)
            if parts is not None:
                for part in getattr(parts, "parts", []) or []:
                    value = getattr(part, "text", None)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        return "I could not generate a response right now."


client = GeminiClient()


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Return a response from Gemini using the configured API key."""
    return client.ask(prompt=prompt, history=history)
