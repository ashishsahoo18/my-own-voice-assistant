"""Data models for OLIVER 2.0 Coding Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CodeExplanationResult:
    """Detailed explanation of code logic, complexity, and control flow."""

    language: str
    summary: str
    line_by_line: list[dict[str, str]] = field(default_factory=list)
    control_flow: str = ""
    time_complexity: str = "Unknown / Not Applicable"
    space_complexity: str = "Unknown / Not Applicable"
    edge_cases: list[str] = field(default_factory=list)
    is_offline: bool = False
    disclaimer: str = "Statically analyzed. Code was not compiled or executed."

    def format_markdown(self) -> str:
        md = [f"### 💻 Code Explanation ({self.language})", ""]
        md.append(f"**Summary:**\n{self.summary}\n")

        if self.line_by_line:
            md.append("**Line-by-Line Breakdown:**")
            for item in self.line_by_line:
                lines = item.get("lines", "")
                expl = item.get("explanation", "")
                md.append(f"- **`{lines}`**: {expl}")
            md.append("")

        if self.control_flow:
            md.append(f"**Control Flow:**\n{self.control_flow}\n")

        md.append(f"**Algorithmic Complexity:**")
        md.append(f"- Time Complexity: `{self.time_complexity}`")
        md.append(f"- Space Complexity: `{self.space_complexity}`\n")

        if self.edge_cases:
            md.append("**Potential Edge Cases & Boundary Conditions:**")
            for ec in self.edge_cases:
                md.append(f"- {ec}")
            md.append("")

        md.append(f"> ℹ️ *{self.disclaimer}*")
        return "\n".join(md)


@dataclass
class DiagnosticResult:
    """Diagnosis of compiler errors, exceptions, and stack traces."""

    language: str
    error_type: str
    root_cause: str
    explanation: str
    suggested_fix: str
    location: Optional[str] = None
    is_offline: bool = False
    disclaimer: str = "Diagnostic based on static error analysis. Not executed."

    def format_markdown(self) -> str:
        md = [f"### 🛠️ Error Diagnosis: {self.error_type} ({self.language})", ""]
        if self.location:
            md.append(f"**Location:** `{self.location}`\n")

        md.append(f"**Root Cause:**\n{self.root_cause}\n")
        md.append(f"**Explanation:**\n{self.explanation}\n")
        md.append(f"**Suggested Fix:**\n```\n{self.suggested_fix}\n```\n")
        md.append(f"> ℹ️ *{self.disclaimer}*")
        return "\n".join(md)


@dataclass
class CodeGenerationResult:
    """Generated code with language tags and prerequisites (never auto-executed)."""

    language: str
    code: str
    explanation: str
    prerequisites: list[str] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)
    disclaimer: str = "Model-generated code. Never executed automatically. Test before running."

    def format_markdown(self) -> str:
        md = [f"### 📝 Generated Code ({self.language})", ""]
        lang_tag = self.language.lower().replace("/", "").replace(" ", "")
        md.append(f"```{lang_tag}\n{self.code}\n```\n")

        md.append(f"**Explanation:**\n{self.explanation}\n")

        if self.prerequisites:
            md.append("**Prerequisites & Setup:**")
            for p in self.prerequisites:
                md.append(f"- {p}")
            md.append("")

        if self.edge_cases:
            md.append("**Edge Cases & Caveats:**")
            for ec in self.edge_cases:
                md.append(f"- {ec}")
            md.append("")

        md.append(f"> ⚠️ *{self.disclaimer}*")
        return "\n".join(md)


@dataclass
class PatchResult:
    """Structured unified diff for minimal surgical changes."""

    patch: str
    is_valid: bool
    summary: str
    original_path: Optional[str] = None
    validation_error: Optional[str] = None
    disclaimer: str = "Suggested patch only. Not applied to files automatically."

    def format_markdown(self) -> str:
        target = f" for `{self.original_path}`" if self.original_path else ""
        md = [f"### 🩹 Suggested Patch{target}", ""]

        if not self.is_valid:
            md.append(f"**Status:** ❌ Invalid / Inapplicable Patch")
            if self.validation_error:
                md.append(f"**Validation Error:** {self.validation_error}\n")
            return "\n".join(md)

        md.append(f"**Summary of Changes:**\n{self.summary}\n")
        md.append(f"```diff\n{self.patch}\n```\n")
        md.append(f"> ℹ️ *{self.disclaimer}*")
        return "\n".join(md)


@dataclass
class CodeReviewResult:
    """Static security and bug inspection findings."""

    language: str
    summary: str
    findings: list[dict[str, str]] = field(default_factory=list)
    is_offline: bool = False
    disclaimer: str = "Statically inspected. Code was not compiled or tested in a sandbox."

    def format_markdown(self) -> str:
        md = [f"### 🔍 Code Review ({self.language})", ""]
        md.append(f"**Summary:**\n{self.summary}\n")

        if self.findings:
            md.append("**Findings & Improvement Opportunities:**")
            for f in self.findings:
                sev = f.get("severity", "INFO").upper()
                cat = f.get("category", "General")
                desc = f.get("description", "")
                rec = f.get("recommendation", "")
                icon = "🚨" if sev == "HIGH" else "⚠️" if sev == "MEDIUM" else "ℹ️"
                md.append(f"- {icon} **[{sev}] {cat}:** {desc}")
                if rec:
                    md.append(f"  *Recommendation:* {rec}")
            md.append("")
        else:
            md.append("✅ No obvious bugs or high-severity anti-patterns detected.\n")

        md.append(f"> ℹ️ *{self.disclaimer}*")
        return "\n".join(md)


@dataclass
class LearningHintResult:
    """Progressive educational guidance (Level 1: Hint, Level 2: Concept, Level 3: Solution)."""

    level: int
    level_name: str
    language: str
    content: str
    next_step: Optional[str] = None
    disclaimer: str = "Learning mode: progressive guidance."

    def format_markdown(self) -> str:
        md = [f"### 🎓 Learning Mode — Level {self.level}: {self.level_name} ({self.language})", ""]
        md.append(f"{self.content}\n")
        if self.next_step:
            md.append(f"**Next Step:** {self.next_step}\n")
        md.append(f"> ℹ️ *{self.disclaimer}*")
        return "\n".join(md)
