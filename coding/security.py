"""Security, secret redaction, and prompt injection defense for OLIVER 2.0 Coding Assistant."""

from __future__ import annotations

import logging
import re
from typing import Tuple

logger = logging.getLogger("oliver.coding.security")


class CodeRedactor:
    """Redacts secrets, credentials, private keys, and connection strings from code context."""

    # Multiline private keys (RSA, EC, OpenSSH, PGP)
    PRIVATE_KEY_PATTERN = re.compile(
        r"-----BEGIN\s+(?:[A-Z\s]+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(?:[A-Z\s]+)?PRIVATE\s+KEY-----",
        re.MULTILINE,
    )

    # Database connection strings with embedded passwords (e.g., postgresql://user:pass@host:5432/db)
    DB_CONN_PATTERN = re.compile(
        r"\b(?P<prefix>(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql):\/\/[^\s:]+:)(?P<password>[^\s'\"`]+)@(?P<host>[a-zA-Z0-9_\-\.]+)(?P<port>:\d+)?(?P<suffix>\/[^\s'\"]*)?",
        re.IGNORECASE,
    )

    # API keys and access tokens
    API_KEY_PATTERNS = [
        # OpenAI, GitHub, AWS, GitLab, Slack
        re.compile(r"\b(?:sk|ghp|gho|ghu|ghs|glpat|xoxb|xoxp)[_-][a-zA-Z0-9_\-]{16,}\b"),
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        # JWT token
        re.compile(r"\beyJ[a-zA-Z0-9_\-]{20,}\.eyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-\.]{20,}\b"),
    ]

    # Explicit hardcoded secret assignments in source code:
    # Matches: secret_key = "...", db_password = "..."
    # Avoids false positives on os.environ, os.getenv, input(), None, "", etc.
    SECRET_ASSIGNMENT_PATTERN = re.compile(
        r"(?i)\b(?P<var>api[_-]?key|secret[_-]?key|private[_-]?key|client[_-]?secret|access[_-]?token|db[_-]?password|password)\s*[:=]\s*['\"](?P<val>[a-zA-Z0-9!@#$%^&*_\-\.]{8,})['\"]"
    )

    @classmethod
    def redact(cls, text: str) -> str:
        """Redact secrets from code text while preserving syntax structure and avoiding false positives."""
        if not text:
            return ""

        # 1. Redact multiline private keys
        cleaned = cls.PRIVATE_KEY_PATTERN.sub("[REDACTED_PRIVATE_KEY]", text)

        # 2. Redact passwords in database connection URIs
        def _redact_db_uri(m: re.Match) -> str:
            prefix = m.group("prefix")
            host = m.group("host")
            port = m.group("port") or ""
            suffix = m.group("suffix") or ""
            return f"{prefix}[REDACTED_DB_PASSWORD]@{host}{port}{suffix}"

        cleaned = cls.DB_CONN_PATTERN.sub(_redact_db_uri, cleaned)

        # 3. Redact known API key / token tokens
        for pat in cls.API_KEY_PATTERNS:
            cleaned = pat.sub("[REDACTED_API_TOKEN]", cleaned)

        # 4. Redact hardcoded password / secret string literals
        def _redact_assignment(m: re.Match) -> str:
            var_name = m.group("var")
            val = m.group("val")
            # Avoid redacting placeholder text like "your_api_key_here" or "password123" if requested,
            # but redact actual values safely
            if re.match(r"(?i)^your[_-]?|^dummy|^example|^placeholder|^changeme$", val):
                return m.group(0)
            return f'{var_name} = "[REDACTED_SECRET]"'

        cleaned = cls.SECRET_ASSIGNMENT_PATTERN.sub(_redact_assignment, cleaned)

        return cleaned


class CodePromptDefuser:
    """Isolates untrusted source code and defuses prompt injection attempts in comments or strings."""

    DANGEROUS_PATTERNS = [
        re.compile(r"(?i)ignore\s+(?:all\s+)?previous\s+instructions"),
        re.compile(r"(?i)system\s*:\s*(?:you\s+are\s+now|override|grant)"),
        re.compile(r"(?i)override\s+(?:all\s+)?security\s+policies"),
        re.compile(r"(?i)authorize\s+(?:all\s+)?tools"),
        re.compile(r"(?i)you\s+must\s+execute\s+this\s+command"),
        re.compile(r"(?i)bypass\s+(?:all\s+)?confirmation"),
        re.compile(r"(?i)delete\s+all\s+(?:files|databases)"),
    ]

    @classmethod
    def defuse(cls, code: str) -> str:
        """Sanitize adversarial instruction injection in code comments or docstrings."""
        if not code:
            return ""

        sanitized = code
        for pat in cls.DANGEROUS_PATTERNS:
            sanitized = pat.sub("[DEFUSED_INJECTION_DIRECTIVE]", sanitized)

        return sanitized

    @classmethod
    def wrap_untrusted(cls, code: str, language: str = "Unknown") -> str:
        """Wrap source code in strict untrusted data boundaries with system isolation instructions."""
        redacted = CodeRedactor.redact(code)
        defused = cls.defuse(redacted)

        return (
            f'<untrusted_code_input language="{language}">\n'
            f"{defused}\n"
            f"</untrusted_code_input>"
        )
