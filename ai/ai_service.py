"""Local Ollama AI Service for ASHISH AI."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    requests = None

UNAVAILABLE_MESSAGE = "Local AI is offline. Please start Ollama."


class AIService:
    """Modular Local AI Service with dynamic endpoint probing and model auto-detection."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("ashish.ai_service")
        self.configured_url = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
        self.configured_model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()

    def check_health(self) -> tuple[bool, str, str, list[str], str]:
        """Perform health check on local Ollama service.

        Returns: (is_healthy, active_url, selected_model, available_models, error_message)
        """
        if not requests:
            return False, "", "", [], "Local AI is offline. Please install the requests package."

        # Candidate endpoints to probe
        env_url = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
        candidates = [env_url, "http://127.0.0.1:11434", "http://localhost:11434"]
        
        # Deduplicate preserving order
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
                    json_resp = resp.json()
                    models_data = json_resp.get("models", [])
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
                "No local AI model is installed. Please run 'ollama pull llama3.2' to install a model.",
            )

        # Select configured model if installed, otherwise auto-select first available model
        target_model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
        selected_model = ""

        # Exact match or tag-normalized match (e.g. "llama3.2" matches "llama3.2:latest")
        for m in model_names:
            clean_m = m.split(":")[0]
            if m.lower() == target_model.lower() or clean_m.lower() == target_model.lower():
                selected_model = m
                break

        if not selected_model:
            selected_model = model_names[0]
            self.logger.info("Configured model '%s' missing. Auto-selected installed model '%s'.", target_model, selected_model)

        return True, active_url, selected_model, model_names, ""

    def ask(self, prompt: str) -> str:
        """Generate local AI response using Ollama REST API.

        Does NOT require any cloud API keys.
        Does NOT open web browser or ChatGPT.
        """
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return "Please ask a question."

        # Greeting check
        lowered = clean_prompt.lower()
        if lowered in {"hello ashish ai", "hi ashish ai", "hey ashish ai", "hello", "hi", "hey"}:
            return "Hello! I am ASHISH AI, your personal desktop assistant. How can I help you today?"

        is_healthy, active_url, selected_model, available_models, error_msg = self.check_health()
        if not is_healthy:
            return error_msg

        chat_endpoint = f"{active_url}/api/chat"
        generate_endpoint = f"{active_url}/api/generate"

        system_prompt = (
            "You are ASHISH AI, a helpful, intelligent personal desktop assistant. "
            "Provide clear, accurate, natural, and concise answers suitable for a voice HUD."
        )

        try:
            payload = {
                "model": selected_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": clean_prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 300,
                },
            }

            resp = requests.post(chat_endpoint, json=payload, timeout=15.0)

            if resp.status_code == 200:
                data = resp.json()
                if "message" in data and "content" in data["message"]:
                    return data["message"]["content"].strip()
                if "response" in data:
                    return data["response"].strip()

            # Fallback to /api/generate
            gen_payload = {
                "model": selected_model,
                "prompt": f"{system_prompt}\n\nQuestion: {clean_prompt}\nAnswer:",
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 300,
                },
            }
            gen_resp = requests.post(generate_endpoint, json=gen_payload, timeout=15.0)
            if gen_resp.status_code == 200:
                gen_data = gen_resp.json()
                if "response" in gen_data:
                    return gen_data["response"].strip()

            return f"Local AI model '{selected_model}' returned an error (HTTP {resp.status_code})."

        except Exception as exc:
            self.logger.warning("Ollama query exception: %s", exc)
            return f"Local AI query failed: {exc}"
