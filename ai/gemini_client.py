"""Gemini API client for AYRA AI."""

from __future__ import annotations

import logging
import os
import re
import socket
from collections.abc import Generator
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "ayra.log"

load_dotenv(ENV_PATH)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("ayra")
if not logger.handlers:
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    logger.addHandler(handler)
    logger.propagate = False


class GeminiClient:
    """Google Gemini client using the official GenAI Python SDK."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = self._resolve_model_name()
        self.system_prompt = self._build_system_prompt()
        self.client: Optional[genai.Client] = None

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        """Return a complete Gemini response."""
        if not self._is_configured:
            logger.error("Gemini client is not configured")
            return self._configuration_error_message()

        trimmed_history = self._trim_history(history)

        try:
            contents = self._build_contents(prompt, trimmed_history)
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    top_p=0.95,
                ),
            )
            return self._extract_text(response)
        except ClientError as exc:
            return self._handle_client_error(exc)
        except (socket.timeout, TimeoutError) as exc:
            logger.exception("Gemini request timed out: %s", exc)
            return "The AI request timed out. Please try again."
        except (ConnectionError, OSError, socket.gaierror) as exc:
            logger.exception("Gemini network error: %s", exc)
            return "Unable to connect to the AI service. Please check your internet connection."
        except Exception as exc:
            logger.exception("Unexpected Gemini failure: %s", exc)
            return "The AI service is temporarily unavailable."

    def stream(self, prompt: str, history: Optional[list[dict]] = None) -> Generator[str, None, None]:
        """Yield Gemini response chunks for streaming UIs."""
        if not self._is_configured:
            yield self._configuration_error_message()
            return

        trimmed_history = self._trim_history(history)

        try:
            contents = self._build_contents(prompt, trimmed_history)
            response_stream = self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.7,
                    top_p=0.95,
                ),
            )

            for chunk in response_stream:
                text = self._extract_text(chunk)
                if text:
                    yield text
        except ClientError as exc:
            yield self._handle_client_error(exc)
        except (socket.timeout, TimeoutError):
            yield "The AI request timed out. Please try again."
        except (ConnectionError, OSError, socket.gaierror):
            yield "Unable to connect to the AI service. Please check your internet connection."
        except Exception as exc:
            logger.exception("Unexpected Gemini streaming failure: %s", exc)
            yield "The AI service is temporarily unavailable."

    @property
    def _is_configured(self) -> bool:
        """Return True when the Gemini client can make requests."""
        return bool(self.api_key and self.client)

    def _build_system_prompt(self) -> str:
        """Create AYRA's system prompt."""
        return (
            "You are AYRA AI, a premium futuristic desktop assistant for Ashish. "
            "You are friendly, concise, practical, and highly capable. "
            "You help with coding, debugging, Python, Windows automation, productivity, "
            "file summaries, learning, reminders, notes, web search guidance, and general conversation. "
            "When the user asks for code, provide clean Python 3.13 code with type hints when useful. "
            "When something is uncertain, say so clearly. "
            "Keep answers helpful and direct unless the user asks for deep detail."
        )

    def _resolve_model_name(self) -> str:
        """Resolve Gemini model from environment."""
        configured = os.getenv("GEMINI_MODEL", "").strip()

        if configured.startswith("gemini-"):
            return configured

        return "gemini-1.5-flash"

    def _configuration_error_message(self) -> str:
        """Return a helpful message for missing API configuration."""
        return "Gemini is not configured. Add GEMINI_API_KEY to your .env file."

    def _quota_error_message(self) -> str:
        """Return a quota-specific Gemini error message."""
        retry_delay = "Please wait and try again later."
        return (
            "Gemini quota limit reached. "
            f"{retry_delay} You can also reduce message size or use a paid API key."
        )

    def _handle_client_error(self, exc: ClientError) -> str:
        """Map Gemini client errors to user-friendly messages."""
        status_code = self._extract_status_code(exc)
        logger.exception("Gemini ClientError: %s", exc)

        if self._is_quota_error(exc):
            return self._quota_error_message()

        if status_code == 401:
            return "Gemini API key is invalid. Please verify GEMINI_API_KEY."

        if status_code == 403:
            return "This Gemini API key does not have permission to use the selected model."

        if status_code == 404:
            return f"The Gemini model '{self.model}' was not found. Check GEMINI_MODEL in .env."

        if status_code == 500:
            return "Gemini is temporarily unavailable."

        return "Gemini is temporarily unavailable."

    def _is_quota_error(self, exc: Exception) -> bool:
        """Return True when Gemini indicates a quota/rate-limit problem."""
        status_code = self._extract_status_code(exc)
        if status_code == 429:
            return True

        message = str(exc).lower()
        quota_tokens = [
            "resource_exhausted",
            "quota",
            "free tier",
            "quota exceeded",
            "limit reached",
            "rate limit",
        ]
        return any(token in message for token in quota_tokens)

    def _trim_history(self, history: Optional[list[dict]]) -> list[dict]:
        """Keep recent conversation history small for context control."""
        if not history:
            return []

        trimmed_items: list[dict] = []

        for item in history[-10:]:
            if not isinstance(item, dict):
                continue

            role = item.get("role", "user")
            text = str(item.get("content", "")).strip()

            if not text:
                continue

            trimmed_items.append(
                {
                    "role": role,
                    "content": self._shorten_text(text),
                }
            )

        return trimmed_items

    def _shorten_text(self, text: str, max_chars: int = 320) -> str:
        """Shorten long history items."""
        if len(text) <= max_chars:
            return text

        return text[: max_chars - 3].rstrip() + "..."

    def _build_contents(self, prompt: str, history: Optional[list[dict]]) -> list[dict]:
        """Build Gemini content payload from prompt and chat history."""
        contents: list[dict] = []

        if history:
            for item in history:
                role = item.get("role", "user")
                text = str(item.get("content", "")).strip()

                if not text:
                    continue

                gemini_role = "model" if role == "assistant" else "user"
                contents.append(
                    {
                        "role": gemini_role,
                        "parts": [{"text": text}],
                    }
                )

        contents.append(
            {
                "role": "user",
                "parts": [{"text": self._shorten_text(prompt, max_chars=1600)}],
            }
        )
        return contents

    def _extract_text(self, response: object) -> str:
        """Extract text from Gemini response objects."""
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        candidates = getattr(response, "candidates", None) or []
        if candidates:
            first = candidates[0]
            content = getattr(first, "content", None)

            if content is not None:
                for part in getattr(content, "parts", []) or []:
                    value = getattr(part, "text", None)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        return ""

    def _extract_status_code(self, exc: ClientError) -> Optional[int]:
        """Extract HTTP status from Gemini exceptions."""
        for attr in ("status_code", "code", "http_status"):
            value = getattr(exc, attr, None)
            if isinstance(value, int):
                return value

        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None)

        if response_status is not None:
            return int(response_status)

        return None

    def _extract_retry_delay(self, exc: ClientError) -> float:
        """Extract retry delay from Gemini errors when present."""
        for attr in ("retry_delay", "retry_after", "delay"):
            value = getattr(exc, attr, None)
            if isinstance(value, (int, float)):
                return float(value)

        message = str(exc).lower()

        match = re.search(r"retry in\s+([0-9.]+)", message)
        if match:
            return float(match.group(1))

        match = re.search(r"retry after\s+([0-9.]+)", message)
        if match:
            return float(match.group(1))

        return 0.0


client = GeminiClient()


def generate_ai_response(prompt: str, history: list[dict[str, str]] | None = None) -> str:
    """Generate a response from Gemini, with offline fallback."""
    try:
        return ask_ai(prompt, history=history)
    except Exception:
        return (
            "Gemini is temporarily unavailable, but I am still here. "
            "I can help with opening apps, searching the web, reminders, notes, "
            "screenshots, files, and basic calculations."
        )


def stream_ai_response(
    prompt: str,
    history: Optional[list[dict]] = None,
) -> Generator[str, None, None]:
    """Yield streaming Gemini response chunks."""
    yield from client.stream(prompt=prompt, history=history)


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Backward-compatible wrapper for Gemini responses."""
    return generate_ai_response(prompt=prompt, history=history)