"""Local Ollama LLM Provider for OLIVER 2.0."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from core.config import get_config
from core.errors import LLMUnavailable
from llm.provider import LLMProvider, LLMResponse

try:
    import requests
except ImportError:
    requests = None

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("oliver.llm.ollama")


class OllamaProvider(LLMProvider):
    """Local-first Ollama provider for Llama 3.2 on Windows."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        cfg = get_config()
        self.configured_url = (base_url or cfg.llm.ollama_url).rstrip("/")
        self.configured_model = model or cfg.llm.model
        self.timeout = timeout if timeout is not None else cfg.llm.timeout_seconds
        self.max_retries = cfg.llm.max_retries

    def check_health(self) -> tuple[bool, str, str, list[str], str]:
        """Probe candidate endpoints and verify model availability."""
        if not requests:
            return False, "", "", [], "Requests package is missing. Please install requests."

        candidates = [self.configured_url, "http://127.0.0.1:11434", "http://localhost:11434"]
        unique_candidates = []
        for c in candidates:
            if c and c not in unique_candidates:
                unique_candidates.append(c)

        active_url = ""
        models_data = []

        for candidate in unique_candidates:
            try:
                resp = requests.get(f"{candidate}/api/tags", timeout=2.0)
                if resp.status_code == 200:
                    active_url = candidate
                    models_data = resp.json().get("models", [])
                    break
            except Exception:
                continue

        if not active_url:
            return False, "", "", [], "Local AI is offline. Please start Ollama."

        model_names = [m.get("name", "") for m in models_data if m.get("name")]
        if not model_names:
            return (
                False,
                active_url,
                "",
                [],
                f"No models installed in Ollama. Run 'ollama pull {self.configured_model}' to install.",
            )

        # Match target model or fallback to first available
        selected_model = ""
        for m in model_names:
            clean_m = m.split(":")[0].lower()
            if m.lower() == self.configured_model.lower() or clean_m == self.configured_model.lower():
                selected_model = m
                break

        if not selected_model:
            selected_model = model_names[0]

        return True, active_url, selected_model, model_names, ""

    def ask(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Query Ollama and return generated text."""
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return "Please provide a query."

        is_healthy, active_url, selected_model, _, err_msg = self.check_health()
        if not is_healthy:
            return err_msg

        sys_prompt = system_prompt or (
            "You are OLIVER, a personal desktop AI assistant for Windows. "
            "Provide concise, helpful, and natural answers suitable for a voice assistant."
        )

        chat_url = f"{active_url}/api/chat"
        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": clean_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 300},
        }

        try:
            resp = requests.post(chat_url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if "message" in data and "content" in data["message"]:
                    return data["message"]["content"].strip()
                if "response" in data:
                    return data["response"].strip()

            # Fallback to /api/generate
            gen_url = f"{active_url}/api/generate"
            gen_payload = {
                "model": selected_model,
                "prompt": f"{sys_prompt}\n\nUser: {clean_prompt}\nAssistant:",
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 300},
            }
            gen_resp = requests.post(gen_url, json=gen_payload, timeout=self.timeout)
            if gen_resp.status_code == 200:
                return gen_resp.json().get("response", "").strip()

            return f"Ollama model error (HTTP {resp.status_code})."

        except Exception as exc:
            logger.warning("Ollama ask exception: %s", exc)
            if "timeout" in str(exc).lower():
                return "Local AI is taking longer than expected. Please try again."
            return f"Local AI query failed: {exc}"

    def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
    ) -> Optional[T]:
        """Request structured JSON response parsed and validated into Pydantic schema."""
        is_healthy, active_url, selected_model, _, _ = self.check_health()
        if not is_healthy:
            return None

        # Build schema instructions
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        sys_prompt = (system_prompt or "") + (
            f"\nYou must respond ONLY with valid JSON conforming to this JSON Schema:\n{schema_json}\n"
            "Do not include any surrounding markdown fences, commentary, or text outside the JSON object."
        )

        chat_url = f"{active_url}/api/chat"
        current_prompt = prompt

        for attempt in range(max_retries + 1):
            payload = {
                "model": selected_model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": current_prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 250},
            }

            try:
                resp = requests.post(chat_url, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    content = (
                        data.get("message", {}).get("content", "")
                        or data.get("response", "")
                    ).strip()

                    # Extract JSON if model wrapped in markdown
                    json_str = self._extract_json_substring(content)
                    parsed_dict = json.loads(json_str)
                    return schema.model_validate(parsed_dict)

            except (json.JSONDecodeError, ValidationError) as parse_err:
                logger.warning("Structured output validation failed (attempt %d): %s", attempt + 1, parse_err)
                current_prompt = f"Previous response was invalid JSON: {parse_err}. Please fix and provide ONLY valid JSON."
            except Exception as exc:
                logger.warning("Ollama connection exception during structured output: %s", exc)
                break

        return None

    def _extract_json_substring(self, text: str) -> str:
        """Extract JSON block from text."""
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            return brace_match.group(1)
        return text
