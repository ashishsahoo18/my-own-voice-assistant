"""OLIVER 2.0 LLM provider package."""

from llm.ollama_provider import OllamaProvider
from llm.provider import LLMProvider, LLMResponse

_global_llm_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Return default configured LLM provider singleton."""
    global _global_llm_provider
    if _global_llm_provider is None:
        _global_llm_provider = OllamaProvider()
    return _global_llm_provider


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OllamaProvider",
    "get_llm_provider",
]
