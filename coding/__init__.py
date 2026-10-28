"""OLIVER 2.0 Coding Assistant package.

Provides safe, static-first programming capabilities:
- Code explanation & Big-O complexity estimation
- Error diagnosis & traceback inspection
- Safe code generation (never auto-executed)
- Structured unified diff patch generation (never auto-applied)
- Code review and security inspection
- Progressive mentorship and learning mode
"""

from __future__ import annotations

from coding.analyzer import CodeAnalyzer
from coding.diff_engine import DiffEngine
from coding.languages import LanguageDetector
from coding.models import (
    CodeExplanationResult,
    CodeGenerationResult,
    CodeReviewResult,
    DiagnosticResult,
    LearningHintResult,
    PatchResult,
)
from coding.security import CodePromptDefuser, CodeRedactor
from coding.service import CodingService

__all__ = [
    "CodingService",
    "CodeAnalyzer",
    "DiffEngine",
    "LanguageDetector",
    "CodePromptDefuser",
    "CodeRedactor",
    "CodeExplanationResult",
    "DiagnosticResult",
    "CodeGenerationResult",
    "PatchResult",
    "CodeReviewResult",
    "LearningHintResult",
]
