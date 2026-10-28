"""Coding Assistant skill for OLIVER 2.0.

Provides read-only code explanation, error diagnosis, generation, patch formatting,
code review, and learning mode guidance. Never executes code or modifies files automatically.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from coding.models import (
    CodeExplanationResult,
    CodeGenerationResult,
    CodeReviewResult,
    DiagnosticResult,
    LearningHintResult,
    PatchResult,
)
from coding.service import CodingService
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec

logger = logging.getLogger("oliver.skills.coding")


class CodingSkill(BaseSkill):
    """Safe, read-only programming assistant skill for OLIVER 2.0."""

    def __init__(self, service: Optional[CodingService] = None) -> None:
        super().__init__()
        self.service = service or CodingService()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="coding",
            version="1.0.0",
            description="Safe coding assistant: explains code, diagnoses errors, generates code, produces minimal patches, reviews for bugs, and provides progressive learning hints.",
            triggers=[
                "explain code",
                "diagnose error",
                "help fix error",
                "generate code",
                "review code",
                "code patch",
                "give hint",
            ],
            dependencies=[],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="coding.explain",
                description="Explain code logic line-by-line, control flow, edge cases, and algorithmic complexity.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.explain,
            ),
            ToolSpec(
                name="coding.diagnose_error",
                description="Diagnose compiler errors, syntax errors, and stack traces.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.diagnose_error,
            ),
            ToolSpec(
                name="coding.generate",
                description="Generate readable, documented code without executing it.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.generate,
            ),
            ToolSpec(
                name="coding.generate_patch",
                description="Produce minimal unified diff patches without applying them to disk.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.generate_patch,
            ),
            ToolSpec(
                name="coding.review",
                description="Statically review code for potential bugs, security issues, and edge cases.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.review,
            ),
            ToolSpec(
                name="coding.learning_hint",
                description="Provide progressive learning guidance (Level 1: hint, Level 2: concept, Level 3: solution).",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.learning_hint,
            ),
        ]

    def explain(self, code: str, language: Optional[str] = None) -> ToolResult:
        """Explain code logic, complexity, and control flow."""
        clean = (code or "").strip()
        if not clean:
            return ToolResult(status="FAILED", message="Code parameter cannot be empty.")

        res: CodeExplanationResult = self.service.explain(clean, language=language)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={
                "language": res.language,
                "summary": res.summary,
                "time_complexity": res.time_complexity,
                "space_complexity": res.space_complexity,
                "is_offline": res.is_offline,
            },
        )

    def diagnose_error(
        self,
        error_log: str,
        code: Optional[str] = None,
        language: Optional[str] = None,
    ) -> ToolResult:
        """Diagnose compiler error or stack trace."""
        clean_log = (error_log or "").strip()
        if not clean_log:
            return ToolResult(status="FAILED", message="Error log cannot be empty.")

        res: DiagnosticResult = self.service.diagnose_error(clean_log, code=code, language=language)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={
                "language": res.language,
                "error_type": res.error_type,
                "location": res.location,
                "root_cause": res.root_cause,
                "is_offline": res.is_offline,
            },
        )

    def generate(self, prompt: str, language: str = "Python") -> ToolResult:
        """Generate formatted code without executing it."""
        clean_prompt = (prompt or "").strip()
        if not clean_prompt:
            return ToolResult(status="FAILED", message="Generation prompt cannot be empty.")

        res: CodeGenerationResult = self.service.generate(clean_prompt, language=language)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={
                "language": res.language,
                "code": res.code,
                "explanation": res.explanation,
            },
        )

    def generate_patch(
        self,
        original_code: str,
        target_code: str,
        file_path: Optional[str] = None,
    ) -> ToolResult:
        """Produce unified diff patch without modifying disk."""
        res: PatchResult = self.service.generate_patch(
            original_code or "",
            target_code or "",
            file_path=file_path,
        )
        status = "SUCCESS" if res.is_valid else "FAILED"
        return ToolResult(
            status=status,
            message=res.format_markdown(),
            data={
                "patch": res.patch,
                "is_valid": res.is_valid,
                "validation_error": res.validation_error,
                "original_path": res.original_path,
            },
        )

    def review(self, code: str, language: Optional[str] = None) -> ToolResult:
        """Statically inspect code for bugs, anti-patterns, and security concerns."""
        clean = (code or "").strip()
        if not clean:
            return ToolResult(status="FAILED", message="Code parameter cannot be empty.")

        res: CodeReviewResult = self.service.review(clean, language=language)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={
                "language": res.language,
                "summary": res.summary,
                "findings_count": len(res.findings),
                "is_offline": res.is_offline,
            },
        )

    def learning_hint(
        self,
        problem_or_code: str,
        level: int = 1,
        language: Optional[str] = None,
    ) -> ToolResult:
        """Provide progressive learning mentorship."""
        clean = (problem_or_code or "").strip()
        if not clean:
            return ToolResult(status="FAILED", message="Problem or code parameter cannot be empty.")

        res: LearningHintResult = self.service.learning_hint(clean, level=level, language=language)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={
                "level": res.level,
                "level_name": res.level_name,
                "language": res.language,
                "content": res.content,
            },
        )
