"""AI Provider abstraction layer and local Ollama implementation for OLIVER 3.0."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Tuple

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger

# Reuse exact system prompt and unavailable message from OLIVER 2.0 (ai/ai_service.py)
SYSTEM_PROMPT = (
    "You are OLIVER 3.0 (also known as ASHISH AI), an intelligent, privacy-conscious personal AI assistant for Windows and mobile, created by Ashish Sahoo.\n\n"
    "Guidelines for your responses:\n"
    "1. Give direct, accurate, and helpful answers immediately.\n"
    "2. For programming questions (Python, Flutter, Dart, C++, Java, JavaScript, Django, MERN stack, DSA, algorithms, and system design), provide clear explanations with concise, well-commented code examples when relevant.\n"
    "3. For mathematics, science, and computer science fundamentals, explain complex concepts using simple analogies and rigorous technical clarity.\n"
    "4. For interview preparation and professional communication, provide articulate, high-standard, structured advice.\n"
    "5. Be concise and natural, suited for both a screen interface and spoken audio output.\n"
    "6. If you are uncertain or the topic requires current real-time data beyond offline knowledge, state this truthfully without inventing facts."
)

UNAVAILABLE_MESSAGE = "Local AI is offline. Please start Ollama."


class AIProvider(ABC):
    """Abstract interface for OLIVER AI inference providers."""

    @abstractmethod
    async def generate_response(self, prompt: str, system_prompt: str = SYSTEM_PROMPT) -> Tuple[str, float]:
        """Generate response given prompt. Returns (reply_text, latency_ms)."""
        pass

    @abstractmethod
    async def check_health(self) -> Tuple[bool, str, str]:
        """Check provider health. Returns (is_healthy, selected_model, error_message)."""
        pass


class OllamaProvider(AIProvider):
    """Local Ollama AI inference provider reusing OLIVER 2.0 parameters."""

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    async def check_health(self) -> Tuple[bool, str, str]:
        """Query Ollama tags endpoint to determine service and model availability."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check if configured model or prefix exists
                    for m in models:
                        if m.startswith(self.model) or self.model in m:
                            return True, m, ""
                    if models:
                        return True, models[0], f"Configured model '{self.model}' not found; using '{models[0]}'"
                    return True, self.model, ""
                return False, self.model, f"Ollama HTTP {resp.status_code}"
        except Exception as exc:
            return False, self.model, f"{UNAVAILABLE_MESSAGE} ({type(exc).__name__})"

    async def generate_response(self, prompt: str, system_prompt: str = SYSTEM_PROMPT) -> Tuple[str, float]:
        """Generate response from local Ollama chat API."""
        clean = prompt.strip()
        if not clean:
            return "Please ask a question.", 0.0

        # Check friendly greetings locally for ultra-low latency
        lowered = clean.lower()
        if lowered in {"hello", "hi", "hey", "hello oliver", "hi oliver", "hey oliver", "hello ashish ai"}:
            return "Hello! I am OLIVER, your personal AI assistant. How can I help you today?", 1.0

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": clean},
            ],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 400,
            },
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                if resp.status_code == 200:
                    data = resp.json()
                    message = data.get("message", {}).get("content", "").strip()
                    return message or "I received an empty response from local AI.", elapsed_ms
                else:
                    return f"{UNAVAILABLE_MESSAGE} (Ollama returned HTTP {resp.status_code})", elapsed_ms
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.warning("Ollama connection exception: %s", exc)
            return f"{UNAVAILABLE_MESSAGE}", elapsed_ms


# Global provider instance
ai_provider: AIProvider = OllamaProvider()

