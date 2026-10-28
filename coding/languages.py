"""Language identification and syntax heuristics for OLIVER 2.0 Coding Assistant."""

from __future__ import annotations

import os
import re
from typing import Optional


class LanguageDetector:
    """Detects programming and markup languages from code contents, filenames, or explicit hints."""

    EXTENSION_MAP = {
        ".py": "Python",
        ".pyw": "Python",
        ".cpp": "C++",
        ".cxx": "C++",
        ".cc": "C++",
        ".hpp": "C++",
        ".h": "C/C++",
        ".c": "C",
        ".js": "JavaScript",
        ".jsx": "JavaScript (React)",
        ".ts": "TypeScript",
        ".tsx": "TypeScript (React)",
        ".html": "HTML",
        ".htm": "HTML",
        ".css": "CSS",
        ".scss": "SCSS",
        ".sql": "SQL",
        ".rs": "Rust",
        ".go": "Go",
        ".java": "Java",
        ".sh": "Bash",
        ".bash": "Bash",
        ".ps1": "PowerShell",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".md": "Markdown",
    }

    PATTERNS: list[tuple[re.Pattern, str, int]] = [
        # Django (Higher priority check before generic Python / HTML)
        (re.compile(r"\b(models\.(?:Model|CharField|ForeignKey)|render\s*\(\s*request|forms\.(?:Form|ModelForm)|urlpatterns\s*=|django\.urls|django\.contrib)\b"), "Django (Python)", 10),
        (re.compile(r"(\{%\s*(?:block|extends|for|if|csrf_token)\b|\{\{\s*\w+.*?\}\})"), "Django Template (HTML)", 10),

        # Python
        (re.compile(r"^\s*(?:def\s+\w+\s*\(|class\s+\w+(?:\(.*\))?:|import\s+\w+|from\s+\w+\s+import|if\s+__name__\s*==\s*['\"]__main__['\"]:|elif\s+|print\s*\(|except\s+\w+.*?:)"), "Python", 8),
        (re.compile(r"\b(?:self\.\w+|__init__|lambda\s+\w+:|None|True|False|async\s+def)\b"), "Python", 6),

        # C++
        (re.compile(r"#include\s*<[a-zA-Z0-9_]+>"), "C++", 9),
        (re.compile(r"\b(?:std::(?:cout|cin|endl|vector|string|map|shared_ptr)|nullptr|template\s*<|constexpr|class\s+\w+\s*\{|using\s+namespace\s+std;)\b"), "C++", 8),
        (re.compile(r"\b(?:int\s+main\s*\([^)]*\)\s*\{|cout\s*<<|cin\s*>>)\b"), "C++", 7),

        # JavaScript / TypeScript
        (re.compile(r"\b(?:const\s+\w+\s*=|let\s+\w+\s*=|function\s+\w+\s*\(|console\.(?:log|error|warn)\(|=>\s*\{|import\s+.*?from\s+['\"][^'\"]+['\"];?)"), "JavaScript", 8),
        (re.compile(r"\b(?:interface\s+\w+\s*\{|type\s+\w+\s*=|:\s*(?:string|number|boolean|any)\[\]|export\s+default\s+function)\b"), "TypeScript", 9),

        # HTML / CSS
        (re.compile(r"<!DOCTYPE\s+html>|<html\b|<body\b|<div\b|<head\b|<script\b|<style\b"), "HTML", 9),
        (re.compile(r"\b(?:body|html|\.[\w-]+|#[\w-]+)\s*\{"), "CSS", 5),
        (re.compile(r"^\s*(?:margin|padding|display|color|background|font-size|border|width|height|box-sizing)\s*:[^;]+;"), "CSS", 7),

        # SQL
        (re.compile(r"\b(?:SELECT\s+.*?\s+FROM|INSERT\s+INTO\s+\w+|UPDATE\s+\w+\s+SET|DELETE\s+FROM\s+\w+|CREATE\s+TABLE\s+\w+|PRIMARY\s+KEY|FOREIGN\s+KEY)\b", re.IGNORECASE), "SQL", 9),

        # Rust
        (re.compile(r"\b(?:fn\s+main\s*\(\)|pub\s+struct\s+\w+|impl\s+\w+|let\s+mut\s+\w+|println!\()"), "Rust", 8),

        # Go
        (re.compile(r"\b(?:package\s+main|func\s+main\s*\(\)|fmt\.(?:Println|Printf)|import\s+\(\s*\"fmt\"\s*\))"), "Go", 8),

        # Java
        (re.compile(r"\b(?:public\s+static\s+void\s+main|System\.out\.println|public\s+class\s+\w+)"), "Java", 8),

        # Shell
        (re.compile(r"^#!\s*/bin/(?:bash|sh)"), "Bash", 10),
    ]

    @classmethod
    def detect(cls, code: str, file_path: Optional[str] = None, explicit_hint: Optional[str] = None) -> str:
        """Detect language from hint, file extension, or content heuristic."""
        if explicit_hint and explicit_hint.strip():
            hint_clean = explicit_hint.strip().lower()
            normalized = cls.normalize_language_name(hint_clean)
            if normalized != "Unknown":
                return normalized

        if file_path:
            _, ext = os.path.splitext(file_path.lower())
            if ext in cls.EXTENSION_MAP:
                return cls.EXTENSION_MAP[ext]

        text = (code or "").strip()
        if not text:
            return "Unknown"

        scores: dict[str, int] = {}
        for line in text.splitlines()[:50]:  # Inspect first 50 lines
            for pattern, lang, weight in cls.PATTERNS:
                if pattern.search(line):
                    scores[lang] = scores.get(lang, 0) + weight

        if scores:
            best_lang = max(scores.items(), key=lambda x: x[1])[0]
            return best_lang

        return "Unknown"

    @classmethod
    def normalize_language_name(cls, name: str) -> str:
        """Map user input aliases to canonical language names."""
        n = name.strip().lower()
        if n in ("py", "python", "python3"):
            return "Python"
        if n in ("cpp", "c++", "cplusplus", "cc"):
            return "C++"
        if n in ("c", "clang"):
            return "C"
        if n in ("js", "javascript", "node", "nodejs"):
            return "JavaScript"
        if n in ("ts", "typescript"):
            return "TypeScript"
        if n in ("html", "htm"):
            return "HTML"
        if n in ("css", "stylesheet"):
            return "CSS"
        if n in ("django", "dj"):
            return "Django"
        if n in ("sql", "mysql", "postgres", "postgresql", "sqlite"):
            return "SQL"
        if n in ("rust", "rs"):
            return "Rust"
        if n in ("go", "golang"):
            return "Go"
        if n in ("java",):
            return "Java"
        if n in ("bash", "sh", "shell"):
            return "Bash"
        if n in ("powershell", "ps1"):
            return "PowerShell"
        return "Unknown"
