"""Local AI reasoning and conversation skill for OLIVER 2.0."""

from __future__ import annotations

from ai.ai_service import AIService
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class AISkill(BaseSkill):
    """Adapter wrapping Ollama Local AI Q&A and technical explanation capabilities."""

    def __init__(self) -> None:
        super().__init__()
        self.ai_service = AIService()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="ai",
            version="1.0.0",
            description="Answer questions, explain concepts, and generate technical summaries using local Ollama.",
            triggers=["what is", "explain", "how does", "difference between", "tell me about"],
            dependencies=["requests"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="ai.ask",
                description="Query local Ollama model for concise technical or conversational answer.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.ask,
            ),
        ]

    def health_check(self) -> tuple[bool, str]:
        is_healthy, active_url, model, _, err = self.ai_service.check_health()
        if is_healthy:
            return True, f"Ollama online at {active_url} (model: {model})"
        return False, err or "Ollama offline"

    def ask(self, prompt: str) -> ToolResult:
        res = self.ai_service.ask(prompt)
        status = "FAILED" if "Local AI is offline" in res else "SUCCESS"
        return ToolResult(status=status, message=res, data={"prompt": prompt})
