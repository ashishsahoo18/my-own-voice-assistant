import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()


class GeminiClient:
    """Thin wrapper for the Google Gemini REST API."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.base_url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        self.system_prompt = (
            "You are Ayra, a warm and capable AI assistant. "
            "Answer clearly, politely, and concisely. "
            "Support coding, productivity, web help, and general conversation."
        )

    def ask(self, prompt: str, history: Optional[list[dict]] = None) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not found. Set it in .env first.")

        payload = self._build_payload(prompt, history)

        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return self._extract_text(data)
        except requests.RequestException as exc:
            raise RuntimeError(f"Gemini API request failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError(f"Gemini API returned invalid JSON: {exc}") from exc

    def _build_payload(self, prompt: str, history: Optional[list[dict]]) -> dict:
        contents: list[dict] = []

        if history:
            for item in history:
                role = item.get("role", "user")
                text = item.get("content", "")
                if role == "assistant":
                    contents.append({"role": "model", "parts": [{"text": text}]})
                else:
                    contents.append({"role": "user", "parts": [{"text": text}]})

        contents.append(
            {
                "role": "user",
                "parts": [{"text": f"{self.system_prompt}\n\nUser: {prompt}"}],
            }
        )
        return {"contents": contents}

    def _extract_text(self, data: dict) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("Gemini returned no response parts.")

        text = parts[0].get("text", "")
        return text.strip() or "I could not generate a response right now."


client = GeminiClient()


def ask_ai(prompt: str, history: Optional[list[dict]] = None) -> str:
    """Send a prompt to Gemini and return the assistant response."""
    return client.ask(prompt=prompt, history=history)