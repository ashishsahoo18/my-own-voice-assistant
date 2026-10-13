"""Security guardrails, path validation, and prompt injection defense for Documents & Knowledge."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from coding.security import CodeRedactor
from core.errors import PathSandboxViolation
from security.sandbox import PathSandbox

logger = logging.getLogger("oliver.knowledge.security")


class DocumentSecurity:
    """Enforces file sandboxing, resource bounds, secret redaction, and prompt injection isolation."""

    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB cap
    MAX_CHUNKS = 500

    DANGEROUS_PATTERNS = [
        re.compile(r"(?i)ignore\s+(?:all\s+)?previous\s+instructions"),
        re.compile(r"(?i)system\s*:\s*(?:you\s+are\s+now|override|grant)"),
        re.compile(r"(?i)override\s+(?:all\s+)?security\s+policies"),
        re.compile(r"(?i)authorize\s+(?:all\s+)?tools"),
        re.compile(r"(?i)you\s+must\s+execute\s+this\s+command"),
        re.compile(r"(?i)bypass\s+(?:all\s+)?confirmation"),
        re.compile(r"(?i)delete\s+all\s+(?:files|databases)"),
    ]

    def __init__(self, sandbox: Optional[PathSandbox] = None) -> None:
        self.sandbox = sandbox or PathSandbox()

    def validate_file_path(self, target_path: str | Path) -> Path:
        """Verify that the target path is safe and permitted by the PathSandbox."""
        raw_path = Path(target_path)
        # Sandbox resolves and validates against allowed roots and denied system/credential folders
        resolved = self.sandbox.validate_path(raw_path)

        if not resolved.exists():
            raise FileNotFoundError(f"Document file not found: {resolved}")

        if not resolved.is_file():
            raise ValueError(f"Path is not a regular file: {resolved}")

        # Check file size cap
        file_size = resolved.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File '{resolved.name}' exceeds the maximum allowed size of 20 MB ({file_size} bytes)."
            )

        return resolved

    @classmethod
    def defuse_prompt_injection(cls, text: str) -> str:
        """Neutralize malicious injection instructions inside document text."""
        if not text:
            return ""

        sanitized = text
        for pat in cls.DANGEROUS_PATTERNS:
            sanitized = pat.sub("[DEFUSED_DOCUMENT_DIRECTIVE]", sanitized)
        return sanitized

    @classmethod
    def redact_secrets(cls, text: str) -> str:
        """Redact sensitive keys, passwords, and tokens from document text."""
        return CodeRedactor.redact(text)

    @classmethod
    def wrap_untrusted_context(cls, text: str, filename: str, page_number: int = 1) -> str:
        """Wrap document text in isolated XML boundaries with prompt defusing and secret redaction."""
        redacted = cls.redact_secrets(text)
        defused = cls.defuse_prompt_injection(redacted)

        return (
            f'<untrusted_document_context filename="{filename}" page="{page_number}">\n'
            f"{defused}\n"
            f"</untrusted_document_context>"
        )
