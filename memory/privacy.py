"""Deterministic privacy and sensitivity filter for OLIVER 2.0 Memory Engine.

Ensures that passwords, API keys, tokens, OTPs, payment data, and sensitive secrets
are never persisted into long-term or episodic memory.
The LLM does NOT make privacy decisions; deterministic rule-based checks gate all storage.
"""

from __future__ import annotations

import re
from typing import Tuple


class MemoryPrivacyFilter:
    """Deterministic rules guarding against persisting sensitive user secrets."""

    # Patterns for API keys, tokens, secrets
    SECRET_PATTERNS = [
        # Bearer tokens, JWT
        (r"\b(?:bearer\s+)?[a-zA-Z0-9_\-\.]{20,}\.[a-zA-Z0-9_\-\.]{20,}\.[a-zA-Z0-9_\-\.]+\b", "JWT/Bearer token"),
        # OpenAI, Anthropic, HuggingFace, GitHub, AWS tokens
        (r"\b(?:sk|ghp|gho|ghu|ghs|glpat|AKIA|ASIA)-[a-zA-Z0-9_\-]{16,}\b", "API key / Access token"),
        # Generic API key assignments: api_key = "...", secret: ...
        (r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{8,}['\"]?", "API credential"),
    ]

    # Patterns for Passwords
    PASSWORD_PATTERNS = [
        (r"(?i)\b(?:my\s+)?password\s*(?:is|:|=)\s*['\"]?\S+['\"]?", "Password assignment"),
        (r"(?i)\b(?:passcode|pin|master\s+pass)\s*(?:is|:|=)\s*['\"]?\S+['\"]?", "Passcode / PIN assignment"),
    ]

    # Patterns for OTPs and verification codes
    OTP_PATTERNS = [
        (r"(?i)\b(?:otp|one-time\s+password|verification\s+code|security\s+code)\s*(?:is|:|=)?\s*\b\d{4,8}\b", "One-time passcode (OTP)"),
        (r"\b\d{4,8}\s+(?:is\s+your\s+(?:otp|verification\s+code))\b", "One-time passcode (OTP)"),
    ]

    # Patterns for Payment and Financial credentials
    PAYMENT_PATTERNS = [
        # Credit Card Numbers (13-19 digits, optionally spaced or hyphenated)
        (r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9]{2})[0-9]{12}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11})\b", "Payment card number"),
        (r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}\b", "Credit/Debit card number format"),
        # CVV / CVC
        (r"(?i)\b(?:cvv|cvc|security\s+number)\s*(?:is|:|=)?\s*\d{3,4}\b", "Card CVV/CVC code"),
    ]

    def validate_for_storage(self, text: str) -> Tuple[bool, str]:
        """Check if content is safe to store in memory.
        
        Returns:
            (is_safe, violation_reason)
        """
        if not text or not text.strip():
            return False, "Empty content cannot be stored."

        # Check all secret patterns
        for pattern, label in self.SECRET_PATTERNS:
            if re.search(pattern, text):
                return False, f"Contains sensitive data: {label}."

        # Check password patterns
        for pattern, label in self.PASSWORD_PATTERNS:
            if re.search(pattern, text):
                return False, f"Contains sensitive data: {label}."

        # Check OTP patterns
        for pattern, label in self.OTP_PATTERNS:
            if re.search(pattern, text):
                return False, f"Contains sensitive data: {label}."

        # Check payment patterns
        for pattern, label in self.PAYMENT_PATTERNS:
            if re.search(pattern, text):
                return False, f"Contains sensitive data: {label}."

        return True, ""

    def redact(self, text: str) -> str:
        """Return a safe redacted version of text for display or logging."""
        sanitized = text
        for pattern, label in self.SECRET_PATTERNS:
            sanitized = re.sub(pattern, f"[REDACTED_{label.upper().replace(' ', '_')}]", sanitized)
        for pattern, label in self.PASSWORD_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED_PASSWORD]", sanitized)
        for pattern, label in self.OTP_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED_OTP]", sanitized)
        for pattern, label in self.PAYMENT_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED_PAYMENT_INFO]", sanitized)
        return sanitized


SensitiveDataFilter = MemoryPrivacyFilter
