"""Structured, redacted, and correlated logging for OLIVER 2.0."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

# Context variable for request correlation tracking
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="system"
)

# Common regex patterns for secret and sensitive data detection
SECRET_PATTERNS = [
    # OpenAI / Anthropic / Generic API keys
    (re.compile(r"(sk-[a-zA-Z0-9_\-]{20,})", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # Google API Keys
    (re.compile(r"(AIza[0-9A-Za-z-_]{35})", re.IGNORECASE), "[REDACTED_GOOGLE_KEY]"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+[a-zA-Z0-9_\-\.]{16,})", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # Passwords in env/urls/params
    (re.compile(r"(password\s*[:=]\s*['\"]?)([^'\"\s]+)", re.IGNORECASE), r"\1[REDACTED_PASSWORD]"),
    (re.compile(r"(app_password\s*[:=]\s*['\"]?)([^'\"\s]+)", re.IGNORECASE), r"\1[REDACTED_PASSWORD]"),
    # Credit card / 16-digit patterns
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED_CARD_NUMBER]"),
]


def redact_sensitive_text(text: str) -> str:
    """Redact known secret patterns from string."""
    if not isinstance(text, str):
        return text

    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    """Logging formatter that injects correlation IDs and redacts secrets."""

    def format(self, record: logging.LogRecord) -> str:
        # Inject correlation ID into record
        record.correlation_id = correlation_id_var.get()
        original_message = super().format(record)
        return redact_sensitive_text(original_message)


class AuditLogger:
    """Append-only structured audit logger producing JSON Lines."""

    def __init__(self, audit_file: Path) -> None:
        self.audit_file = audit_file
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)

    def record_event(
        self,
        event_type: str,
        action: str,
        risk_level: int,
        status: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Write an immutable audit entry to audit.jsonl."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": correlation_id_var.get(),
            "event_type": event_type,
            "action": redact_sensitive_text(action),
            "risk_level": risk_level,
            "status": status,
            "details": details or {},
        }
        clean_json = json.dumps(entry, ensure_ascii=False)
        try:
            with self.audit_file.open("a", encoding="utf-8") as f:
                f.write(clean_json + "\n")
        except Exception:
            pass


_audit_logger: Optional[AuditLogger] = None


def setup_logging(
    logs_dir: Optional[Path] = None,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Configure root and application logging with rotation and redaction."""
    global _audit_logger

    base_dir = Path(__file__).resolve().parent.parent
    target_logs_dir = logs_dir or (base_dir / "logs")
    target_logs_dir.mkdir(parents=True, exist_ok=True)

    log_path = target_logs_dir / "oliver.log"
    audit_path = target_logs_dir / "audit.jsonl"

    _audit_logger = AuditLogger(audit_path)

    # Format: [TIMESTAMP] [LEVEL] [CORRELATION_ID] [LOGGER] MESSAGE
    format_str = "%(asctime)s [%(levelname)s] [%(correlation_id)s] [%(name)s]: %(message)s"
    formatter = RedactingFormatter(format_str)

    # Root Logger Configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Rotating File Handler
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with structured formatting."""
    return logging.getLogger(name)


def set_correlation_id(corr_id: str) -> None:
    """Set current correlation ID for request tracking."""
    correlation_id_var.set(corr_id)


def get_audit_logger() -> AuditLogger:
    """Return audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        base_dir = Path(__file__).resolve().parent.parent
        _audit_logger = AuditLogger(base_dir / "logs" / "audit.jsonl")
    return _audit_logger
