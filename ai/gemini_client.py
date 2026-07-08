import logging
import os
import re
import socket
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ClientError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "ayra.log"

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
            logger.error("GEMINI_API_KEY is missing")
            return "The AI service is not configured correctly. Please verify the API key."

        if not self.client:
            logger.error("Gemini client is not configured")
            return "The AI service is not configured correctly. Please verify the API key."

        trimmed_history = self._trim_history(history)

        try:
            contents = self._build_contents(prompt, trimmed_history)
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=self.system_prompt),
            )
            return self._extract_text(response)
        except ClientError as exc:
            status_code = self._extract_status_code(exc)
            logger.exception("Gemini ClientError: %s", exc)
            if self._is_quota_error(exc):
                return self._quota_error_message()
            if status_code == 401:
                return "The AI service is not configured correctly. Please verify the API key."
            if status_code == 403:
                return "This API key does not have permission to use the selected model."
            if status_code == 500:
                return "The AI service is temporarily unavailable."
            return "The AI service is temporarily unavailable."
        except (socket.timeout, TimeoutError) as exc:
            logger.exception("Gemini request timed out: %s", exc)
            return "The AI request timed out. Please try again."
        except (ConnectionError, OSError, socket.gaierror) as exc:
            logger.exception("Gemini network error: %s", exc)
            return "Unable to connect to the AI service. Please check your internet connection."
        except Exception as exc:
            logger.exception("Unexpected Gemini failure: %s", exc)
            return "The AI service is temporarily unavailable."

    def _resolve_model_name(self) -> str:
        configured = os.getenv("GEMINI_MODEL", "").strip()
        if configured.startswith("gemini-"):
            return configured
        return "gemini-1.5-flash"

    def _quota_error_message(self) -> str:
        return (
            "Gemini free quota limit reached. Please wait and try again, reduce your message size, "
            "or use a paid API key."
        )

    def _is_quota_error(self, exc: Exception) -> bool:
        status_code = self._extract_status_code(exc)
        if status_code == 429:
            return True

        message = str(exc).lower()
        return any(
            token in message
            for token in ["resource_exhausted", "quota", "free tier", "quota exceeded", "limit reached"]
        )

    def _trim_history(self, history: Optional[list[dict]]) -> list[dict]:
        if not history:
            return []

        trimmed_items: list[dict] = []
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "user")
            text = str(item.get("content", "")).strip()
            if not text:
                continue
            trimmed_items.append({"role": role, "content": self._shorten_text(text)})
        return trimmed_items

    def _shorten_text(self, text: str, max_chars: int = 280) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"

    def _build_contents(self, prompt: str, history: Optional[list[dict]]) -> list[dict]:
        contents: list[dict] = []

        if history:
            for item in history:
                role = item.get("role", "user")
                text = str(item.get("content", "")).strip()
                if role == "assistant":
                    contents.append({"role": "model", "parts": [{"text": text}]})
                else:
                    contents.append({"role": "user", "parts": [{"text": text}]})

        contents.append({"role": "user", "parts": [{"text": self._shorten_text(prompt, max_chars=1000)}]})
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

    def _extract_status_code(self, exc: ClientError) -> Optional[int]:
        for attr in ("status_code", "code", "http_status"):
            value = getattr(exc, attr, None)
            if isinstance(value, int):
                return value
        if hasattr(exc, "response") and getattr(exc.response, "status_code", None) is not None:
            return int(exc.response.status_code)
        return None

    def _extract_retry_delay(self, exc: ClientError) -> float:
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


def generate_ai_response(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Return a response from Gemini using the configured API key."""
    return client.ask(prompt=prompt, history=history)


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Backward-compatible wrapper for Gemini responses."""
    return generate_ai_response(prompt=prompt, history=history)
