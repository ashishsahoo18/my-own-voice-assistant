import os
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


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
            message = str(exc).lower()
            if "quota" in message or "rate limit" in message:
                raise RuntimeError("The AI service is currently at capacity. Please try again shortly.") from exc
            if "api key" in message or "unauthorized" in message or "invalid" in message:
                raise RuntimeError("The AI service is not available with the current API configuration. Please check your API key.") from exc
            if "timeout" in message or "timed out" in message:
                raise RuntimeError("I'm unable to connect to the AI service right now. Please try again later.") from exc
            if "connection" in message or "network" in message or "internet" in message or "failed to connect" in message:
                raise RuntimeError("I'm unable to connect to the AI service right now. Please try again later.") from exc
            raise RuntimeError("I'm sorry, I couldn't process that request right now. Please try again later.") from exc

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
