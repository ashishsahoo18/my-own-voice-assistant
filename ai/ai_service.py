"""Personal AI Answering System for ASHISH AI."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
except ImportError:
    pass

try:
    from google import genai
except ImportError:
    genai = None

try:
    import google.generativeai as legacy_genai
except ImportError:
    legacy_genai = None


class AIService:
    """Modular AI Service providing in-HUD conversational and technical Q&A."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("ashish.ai_service")
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize Google GenAI client if GEMINI_API_KEY is available."""
        if not self.api_key:
            return

        if genai is not None:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                self.logger.warning("GenAI Client init error: %s", exc)

        if self.client is None and legacy_genai is not None:
            try:
                legacy_genai.configure(api_key=self.api_key)
                self.client = legacy_genai.GenerativeModel("gemini-1.5-flash")
            except Exception as exc:
                self.logger.warning("Legacy GenAI Client init error: %s", exc)

    def is_available(self) -> bool:
        """Check if AI API key and client are configured."""
        return bool(self.api_key and self.client is not None)

    def ask(self, prompt: str) -> str:
        """Generate AI response for in-HUD Command Console and TTS speech.
        
        Does NOT open browser or ChatGPT.
        Returns unavailable notice if no API key is set.
        """
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return "Please ask a question."

        if not self.is_available():
            # Re-check in case .env was modified at runtime
            self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
            self._init_client()

        if not self.is_available():
            return "AI service is currently unavailable. Please set GEMINI_API_KEY in .env."

        try:
            # System prompt for concise, natural assistant answers
            system_prompt = (
                "You are ASHISH AI, a helpful, intelligent personal AI assistant. "
                "Provide clear, accurate, natural, and concise answers suitable for a voice assistant HUD."
            )

            if genai is not None and hasattr(self.client, "models"):
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"{system_prompt}\n\nQuestion: {clean_prompt}",
                )
                if response and hasattr(response, "text") and response.text:
                    return response.text.strip()

            if legacy_genai is not None and hasattr(self.client, "generate_content"):
                response = self.client.generate_content(
                    f"{system_prompt}\n\nQuestion: {clean_prompt}"
                )
                if response and hasattr(response, "text") and response.text:
                    return response.text.strip()

            return "Could not retrieve response from AI service."
        except Exception as exc:
            self.logger.exception("AI Service exception: %s", exc)
            return f"AI SERVICE ERROR: {exc}"
