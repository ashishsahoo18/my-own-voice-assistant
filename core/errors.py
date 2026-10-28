"""Typed error hierarchy and exception mapping for OLIVER 2.0."""

from __future__ import annotations

from typing import Any, Optional


class OliverError(Exception):
    """Base exception for all OLIVER 2.0 errors."""

    def __init__(
        self,
        message: str,
        user_message: Optional[str] = None,
        code: str = "OLIVER_ERROR",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.user_message = user_message or message
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigError(OliverError):
    """Configuration missing or invalid."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            user_message="I encountered a configuration problem. Please check settings.",
            code="CONFIG_ERROR",
            details=details,
        )


class SecurityError(OliverError):
    """Base security violation error."""

    def __init__(
        self,
        message: str,
        user_message: Optional[str] = None,
        code: str = "SECURITY_VIOLATION",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            user_message=user_message or "Action blocked for security policy reasons.",
            code=code,
            details=details,
        )


class PolicyDenied(SecurityError):
    """Policy engine denied action execution."""

    def __init__(self, reason: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=f"Policy denied execution: {reason}",
            user_message=f"I cannot perform this action: {reason}",
            code="POLICY_DENIED",
            details=details,
        )


class PathSandboxViolation(SecurityError):
    """Access outside allowlisted paths."""

    def __init__(self, path: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=f"Path outside sandbox: {path}",
            user_message="I cannot access files outside allowed workspace folders.",
            code="PATH_SANDBOX_VIOLATION",
            details=details,
        )


class CommandNotAllowed(SecurityError):
    """Arbitrary command execution attempt when disabled."""

    def __init__(self, command: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=f"Arbitrary command execution is disabled: {command}",
            user_message="Direct shell command execution is disabled for safety.",
            code="COMMAND_NOT_ALLOWED",
            details=details,
        )


class UserCancelled(OliverError):
    """User cancelled a confirmation dialog or action."""

    def __init__(self, action: str = "action") -> None:
        super().__init__(
            message=f"User cancelled action: {action}",
            user_message="Operation cancelled.",
            code="USER_CANCELLED",
        )


class VerificationFailed(OliverError):
    """Action was executed but post-execution verification failed."""

    def __init__(
        self,
        action: str,
        evidence: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=f"Verification failed for '{action}': {evidence}",
            user_message=f"I attempted '{action}', but could not verify that it succeeded.",
            code="VERIFICATION_FAILED",
            details=details,
        )


class LLMUnavailable(OliverError):
    """Local LLM or Ollama instance is unreachable."""

    def __init__(self, reason: str = "Ollama is offline") -> None:
        super().__init__(
            message=f"Local LLM is unavailable: {reason}",
            user_message="Local AI is offline. Please start Ollama with 'ollama run llama3.2'.",
            code="LLM_UNAVAILABLE",
        )


class SkillError(OliverError):
    """A registered skill tool failed during execution."""

    def __init__(
        self,
        skill_name: str,
        tool_name: str,
        reason: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=f"Skill '{skill_name}' tool '{tool_name}' failed: {reason}",
            user_message=f"There was a problem executing '{tool_name}': {reason}",
            code="SKILL_ERROR",
            details=details,
        )


class ContactAmbiguityError(OliverError):
    """Contact lookup matched multiple people."""

    def __init__(self, query: str, matches: list[str]) -> None:
        match_str = ", ".join(matches)
        super().__init__(
            message=f"Contact query '{query}' matched multiple entries: {match_str}",
            user_message=f"Which '{query}' do you mean? Matching contacts: {match_str}",
            code="CONTACT_AMBIGUOUS",
            details={"query": query, "matches": matches},
        )


class DeviceUnavailable(OliverError):
    """Microphone or audio output device is unavailable."""

    def __init__(self, device_type: str, reason: str) -> None:
        super().__init__(
            message=f"{device_type} is unavailable: {reason}",
            user_message=f"{device_type} could not be accessed. Please check audio devices.",
            code="DEVICE_UNAVAILABLE",
        )


def format_user_error(exc: Exception) -> str:
    """Format any exception into a clean, safe user-facing message."""
    if isinstance(exc, OliverError):
        return exc.user_message

    if isinstance(exc, ConnectionError):
        return "Local AI is offline. Please start Ollama."

    # Handle standard exceptions gracefully without leaking tracebacks
    exc_str = str(exc).strip().lower()
    if (
        "connection refused" in exc_str
        or "failed to connect" in exc_str
        or "ollama" in exc_str
    ):
        return "Local AI is offline. Please start Ollama."

    if "timeout" in exc_str:
        return "The operation took longer than expected and timed out."

    return "An unexpected issue occurred while processing your request."
