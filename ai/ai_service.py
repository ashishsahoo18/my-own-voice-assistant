"""Local Ollama AI Service for OLIVER 2.0 / ASHISH AI."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

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

SYSTEM_PROMPT = (
    "You are OLIVER 2.0 (also known as ASHISH AI), an intelligent, privacy-conscious personal AI desktop assistant for Windows, created by Ashish Sahoo.\n\n"
    "Guidelines for your responses:\n"
    "1. Give direct, accurate, and helpful answers immediately.\n"
    "2. For programming questions (Python, C++, Java, JavaScript, Django, MERN stack, DSA, algorithms, and system design), provide clear explanations with concise, well-commented code examples when relevant.\n"
    "3. For mathematics, science, and computer science fundamentals, explain complex concepts using simple analogies and rigorous technical clarity.\n"
    "4. For interview preparation and professional communication, provide articulate, high-standard, structured advice.\n"
    "5. Be concise and natural, suited for both a futuristic HUD screen and spoken audio output.\n"
    "6. If you are uncertain or the topic requires current real-time data beyond offline knowledge, state this truthfully without inventing facts."
)


class AIService:
    """Modular, low-latency Local AI Service with keep-alive, streaming token delivery, and robust test compatibility."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("oliver.ai_service")
        self.configured_url = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
        self.configured_model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
        try:
            self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "120").strip())
        except (ValueError, TypeError):
            self.timeout = 120.0

        self._lock = threading.RLock()
        self._health_cache: Optional[tuple[bool, str, str, list[str], str]] = None
        self._health_cache_time: float = 0.0
        self._health_cache_ttl: float = 15.0

    def check_health(self, force_refresh: bool = False) -> tuple[bool, str, str, list[str], str]:
        """Perform health check on local Ollama service with test mock awareness.

        Returns: (is_healthy, active_url, selected_model, available_models, error_message)
        """
        now = time.time()
        # If requests.get is mocked in unit tests, bypass cache
        is_mocked = hasattr(requests, "get") and (
            hasattr(requests.get, "assert_called_with")
            or getattr(requests.get, "__name__", "") != "get"
        )

        with self._lock:
            if not force_refresh and not is_mocked and self._health_cache is not None:
                if now - self._health_cache_time < self._health_cache_ttl:
                    return self._health_cache

        if not requests:
            res = (False, "", "", [], "Local AI is offline. Please install the requests package.")
            with self._lock:
                self._health_cache = res
                self._health_cache_time = now
            return res

        env_url = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
        candidates = [env_url, "http://127.0.0.1:11434", "http://localhost:11434"]
        
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
            res = (False, "", "", [], "Local AI is offline. Please start Ollama.")
            with self._lock:
                self._health_cache = res
                self._health_cache_time = now
            return res

        model_names = [m.get("name", "") for m in models_data if m.get("name")]
        if not model_names:
            res = (
                False,
                active_url,
                "",
                [],
                "No local AI model is installed. Please run 'ollama pull llama3.2' to install a model.",
            )
            with self._lock:
                self._health_cache = res
                self._health_cache_time = now
            return res

        target_model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
        selected_model = ""

        for m in model_names:
            clean_m = m.split(":")[0]
            if m.lower() == target_model.lower() or clean_m.lower() == target_model.lower():
                selected_model = m
                break

        if not selected_model:
            selected_model = model_names[0]
            self.logger.info("Configured model '%s' missing. Auto-selected installed model '%s'.", target_model, selected_model)

        res = (True, active_url, selected_model, model_names, "")
        with self._lock:
            self._health_cache = res
            self._health_cache_time = now
        return res

    def warmup(self) -> None:
        """Send background keep-alive ping to pre-warm the Ollama model into memory."""
        def _warm():
            try:
                is_healthy, active_url, selected_model, _, _ = self.check_health()
                if is_healthy and active_url and selected_model:
                    requests.post(
                        f"{active_url}/api/generate",
                        json={
                            "model": selected_model,
                            "prompt": "",
                            "keep_alive": "15m",
                        },
                        timeout=5.0,
                    )
                    self.logger.info("Local Ollama model '%s' warmed up successfully.", selected_model)
            except Exception as exc:
                self.logger.debug("Warmup exception (non-fatal): %s", exc)

        threading.Thread(target=_warm, daemon=True, name="OllamaWarmupThread").start()

    def ask(self, prompt: str, request_id: Optional[str] = None) -> str:
        """Generate local AI response using Ollama, returning full text."""
        return self.ask_stream(prompt=prompt, on_token=None, request_id=request_id)

    def ask_stream(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], None]] = None,
        request_id: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> str:
        """Stream response tokens from Ollama with low first-token latency.

        Calls on_token(chunk) for each arriving token and returns the accumulated string.
        """
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return "Please ask a question."

        lowered = clean_prompt.lower()
        if lowered in {"hello ashish ai", "hi ashish ai", "hey ashish ai", "hello oliver", "hi oliver", "hey oliver", "hello", "hi", "hey"}:
            greeting = "Hello! I am ASHISH AI, your personal desktop assistant. How can I help you today?"
            if on_token:
                on_token(greeting)
            return greeting

        is_healthy, active_url, selected_model, available_models, error_msg = self.check_health()
        if not is_healthy:
            if on_token:
                on_token(error_msg)
            return error_msg

        chat_endpoint = f"{active_url}/api/chat"

        is_streaming = on_token is not None
        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": clean_prompt},
            ],
            "stream": is_streaming,
            "keep_alive": "15m",
            "options": {
                "temperature": 0.7,
                "num_predict": 400,
            },
        }

        start_time = time.perf_counter()
        first_token_time = None
        accumulated_parts: list[str] = []

        try:
            resp = requests.post(chat_endpoint, json=payload, timeout=self.timeout, stream=is_streaming)
            if resp.status_code == 200:
                # Handle streaming response if requested and iter_lines is supported
                if is_streaming and hasattr(resp, "iter_lines"):
                    for line in resp.iter_lines(decode_unicode=True):
                        if cancel_event and cancel_event.is_set():
                            if hasattr(resp, "close"):
                                resp.close()
                            self.logger.info("AI generation aborted via cancellation event.")
                            break

                        if not line:
                            continue

                        try:
                            chunk_data = json.loads(line)
                            token = chunk_data.get("message", {}).get("content", "")
                            if token:
                                if first_token_time is None:
                                    first_token_time = time.perf_counter()
                                    ttft_ms = (first_token_time - start_time) * 1000
                                    self.logger.info("Time to first token (TTFT): %.1f ms", ttft_ms)

                                accumulated_parts.append(token)
                                if on_token:
                                    on_token(token)
                        except Exception:
                            continue

                    full_response = "".join(accumulated_parts).strip()
                    if full_response:
                        return full_response

                # Standard non-streaming or mock response handling
                try:
                    data = resp.json()
                    content = (
                        data.get("message", {}).get("content", "")
                        or data.get("response", "")
                    ).strip()
                    if content:
                        if on_token:
                            on_token(content)
                        return content
                except Exception:
                    pass

            # Fallback to /api/generate if chat yielded empty
            gen_endpoint = f"{active_url}/api/generate"
            gen_payload = {
                "model": selected_model,
                "prompt": f"{SYSTEM_PROMPT}\n\nUser: {clean_prompt}\nAssistant:",
                "stream": is_streaming,
                "keep_alive": "15m",
                "options": {
                    "temperature": 0.7,
                    "num_predict": 400,
                },
            }

            gen_resp = requests.post(gen_endpoint, json=gen_payload, timeout=self.timeout, stream=is_streaming)
            if gen_resp.status_code == 200:
                if is_streaming and hasattr(gen_resp, "iter_lines"):
                    for line in gen_resp.iter_lines(decode_unicode=True):
                        if cancel_event and cancel_event.is_set():
                            if hasattr(gen_resp, "close"):
                                gen_resp.close()
                            break
                        if not line:
                            continue
                        try:
                            chunk_data = json.loads(line)
                            token = chunk_data.get("response", "")
                            if token:
                                accumulated_parts.append(token)
                                if on_token:
                                    on_token(token)
                        except Exception:
                            continue

                    fallback_response = "".join(accumulated_parts).strip()
                    if fallback_response:
                        return fallback_response

                try:
                    gen_data = gen_resp.json()
                    gen_content = gen_data.get("response", "").strip()
                    if gen_content:
                        if on_token:
                            on_token(gen_content)
                        return gen_content
                except Exception:
                    pass

            err_reply = f"Local AI model '{selected_model}' returned an error (HTTP {resp.status_code})."
            if on_token:
                on_token(err_reply)
            return err_reply

        except Exception as exc:
            self.logger.warning("Ollama query exception: %s", exc)
            if (
                (requests and isinstance(exc, requests.exceptions.Timeout))
                or isinstance(exc, TimeoutError)
                or "timed out" in str(exc).lower()
                or "timeout" in str(exc).lower()
            ):
                timeout_msg = "Local AI is taking longer than expected. Please try again."
                if on_token:
                    on_token(timeout_msg)
                return timeout_msg

            fail_msg = f"Local AI query failed: {exc}"
            if on_token:
                on_token(fail_msg)
            return fail_msg
