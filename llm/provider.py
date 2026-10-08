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
