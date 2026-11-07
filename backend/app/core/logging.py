"""Structured logging module that scrubs secrets, passwords, and tokens."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

# Patterns to mask sensitive information
SENSITIVE_PATTERNS = [
    (re.compile(r'(password["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(secret["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(bearer\s+)([a-zA-Z0-9_\-\.]+)', re.IGNORECASE), r'\1***MASKED***'),
    (re.compile(r'(refresh_token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1***MASKED***\3'),
]


class SensitiveDataFilter(logging.Filter):
    """Filter to redact passwords, JWTs, and secret keys from log output."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            for pattern, repl in SENSITIVE_PATTERNS:
                msg = pattern.sub(repl, msg)
            record.msg = msg

        if record.args:
            if isinstance(record.args, dict):
                redacted_args = {}
                for k, v in record.args.items():
                    if any(s in k.lower() for s in ("pass", "token", "secret", "auth", "key")):
                        redacted_args[k] = "***MASKED***"
                    else:
                        redacted_args[k] = v
                record.args = redacted_args
            elif isinstance(record.args, tuple):
                new_args = []
                for a in record.args:
                    if isinstance(a, str):
                        for pattern, repl in SENSITIVE_PATTERNS:
                            a = pattern.sub(repl, a)
                    new_args.append(a)
                record.args = tuple(new_args)

        return True


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure application-wide structured logger with secret redaction."""
    logger = logging.getLogger("oliver_backend")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)

    return logger


logger = setup_logging()

