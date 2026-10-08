"""Unit and regression tests for core configuration, logging, and error handling."""

from __future__ import annotations

import io
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from core.config import OliverConfig, get_config, reload_config
from core.errors import (
    CommandNotAllowed,
    ConfigError,
    ContactAmbiguityError,
    LLMUnavailable,
    OliverError,
    PathSandboxViolation,
    PolicyDenied,
    VerificationFailed,
    format_user_error,
)
from core.logging import (
    RedactingFormatter,
    get_audit_logger,
    redact_sensitive_text,
    set_correlation_id,
    setup_logging,
)


class CoreConfigTests(unittest.TestCase):
    """Test central typed configuration."""

    def test_default_config_values(self) -> None:
        config = OliverConfig()
        self.assertEqual(config.app_name, os.getenv("APP_NAME", "OLIVER"))
        self.assertEqual(config.version, "2.0.0")
        self.assertEqual(config.llm.model, "llama3.2")
        self.assertEqual(config.llm.ollama_url, "http://localhost:11434")
        self.assertFalse(config.security.allow_arbitrary_commands)
        self.assertEqual(config.router_mode, "legacy")

    def test_environment_override(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_MODEL": "llama3.2:1b", "APP_NAME": "OLIVER_TEST"}):
            config = OliverConfig()
            self.assertEqual(config.llm.model, "llama3.2:1b")
            self.assertEqual(config.app_name, "OLIVER_TEST")

    def test_sandbox_path_check(self) -> None:
        config = OliverConfig()
        root = Path(__file__).resolve().parent.parent.parent
        self.assertTrue(config.is_path_allowed(root / "commands"))
        self.assertTrue(config.is_path_allowed(Path.home() / "Desktop"))
        # System windows folder should not be allowed
        self.assertFalse(config.is_path_allowed(Path("C:/Windows/System32/cmd.exe")))


class CoreLoggingTests(unittest.TestCase):
    """Test secret redaction and structured logging."""

    def test_redaction_api_keys(self) -> None:
        sample = "Error using key sk-1234567890abcdef1234567890 to connect"
        redacted = redact_sensitive_text(sample)
        self.assertNotIn("sk-1234567890abcdef1234567890", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)

    def test_redaction_passwords(self) -> None:
        sample = "smtp login failed for app_password='mySecretAppPass123!'"
        redacted = redact_sensitive_text(sample)
        self.assertNotIn("mySecretAppPass123!", redacted)
        self.assertIn("[REDACTED_PASSWORD]", redacted)

    def test_redaction_credit_cards(self) -> None:
        sample = "User entered card 4111 2222 3333 4444 in form"
        redacted = redact_sensitive_text(sample)
        self.assertNotIn("4111 2222 3333 4444", redacted)
        self.assertIn("[REDACTED_CARD_NUMBER]", redacted)

    def test_formatter_injects_correlation_id(self) -> None:
        set_correlation_id("req-test-999")
        formatter = RedactingFormatter("%(correlation_id)s %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        self.assertIn("req-test-999", output)
        self.assertIn("Hello world", output)


class CoreErrorsTests(unittest.TestCase):
    """Test error hierarchy and user-facing formatting."""

    def test_error_hierarchy(self) -> None:
        err = PolicyDenied("Action is level 3")
        self.assertIsInstance(err, OliverError)
        self.assertEqual(err.code, "POLICY_DENIED")
        self.assertIn("Action is level 3", err.message)

    def test_format_user_error_oliver_error(self) -> None:
        err = LLMUnavailable("Ollama unreachable")
        user_msg = format_user_error(err)
        self.assertIn("Local AI is offline", user_msg)

    def test_format_user_error_generic_exception(self) -> None:
        err = ConnectionRefusedError("Failed to connect to localhost:11434")
        user_msg = format_user_error(err)
        self.assertIn("Local AI is offline", user_msg)

    def test_contact_ambiguity_error(self) -> None:
        err = ContactAmbiguityError("Rahul", ["Rahul Sharma", "Rahul Verma"])
        self.assertIn("Which 'Rahul' do you mean?", err.user_message)
        self.assertIn("Rahul Sharma, Rahul Verma", err.user_message)


if __name__ == "__main__":
    unittest.main()
