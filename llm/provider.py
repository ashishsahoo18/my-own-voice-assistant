"""LLM Provider abstraction for OLIVER 2.0."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMResponse(BaseModel):
    """Standardized LLM response container."""

    content: str
    model: str
    provider: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None


class LLMProvider(ABC):
    """Abstract interface for LLM backends (Ollama, local models, or extensions)."""

    @abstractmethod
    def check_health(self) -> tuple[bool, str, str, list[str], str]:
        """Check if provider is available.

        Returns: (is_healthy, active_url, selected_model, available_models, error_message)
        """
        pass

    @abstractmethod
    def ask(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text response from the model."""
        pass

    @abstractmethod
    def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
    ) -> Optional[T]:
        """Request structured JSON response parsed and validated into a Pydantic schema."""
        pass


class DummyLLMProvider(LLMProvider):
    """Predictable, isolated in-memory LLM provider for unit tests.

    Requires no active server, downloads no models, and allows tests to specify
    canned text and structured responses or simulate timeouts and failures.
    """

    def __init__(
        self,
        canned_response: str = "Mocked LLM test response.",
        is_healthy: bool = True,
        error_message: str = "",
        structured_payload: Optional[dict[str, Any]] = None,
    ) -> None:
        self.canned_response = canned_response
        self.is_healthy = is_healthy
        self.error_message = error_message
        self.structured_payload = structured_payload or {}
        self.call_history: list[dict[str, Any]] = []

    def check_health(self) -> tuple[bool, str, str, list[str], str]:
        if not self.is_healthy:
            return False, "", "", [], self.error_message or "Simulated LLM offline."
        return True, "mock://localhost:11434", "mock-llama3.2", ["mock-llama3.2"], ""

    def ask(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        self.call_history.append({"method": "ask", "prompt": prompt, "system_prompt": system_prompt})
        if not self.is_healthy:
            return self.error_message or "Simulated LLM offline."
        return self.canned_response

    def structured_output(
        self,
        prompt: str,
        schema: Type[T],
        system_prompt: Optional[str] = None,
        max_retries: int = 2,
    ) -> Optional[T]:
        self.call_history.append({"method": "structured_output", "prompt": prompt, "schema": schema.__name__})
        if not self.is_healthy:
            return None
        try:
            return schema.model_validate(self.structured_payload)
        except Exception:
            return None
