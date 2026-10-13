"""Security, SSRF defense, domain allowlisting, and untrusted content sanitization for OLIVER 2.0 Browser Automation."""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from core.config import get_config
from core.errors import SecurityError as CoreSecurityError
from research.security import SSRFValidationError, SecurityError, is_ip_restricted, validate_url

logger = logging.getLogger("oliver.browser.security")


class BrowserSecurityError(CoreSecurityError):
    """Base exception for browser automation security violations."""


class DomainNotAllowedError(BrowserSecurityError):
    """Raised when a URL domain is not permitted under the active allowlist."""


class BrowserSideEffectBlockedError(BrowserSecurityError):
    """Raised when a requested browser action would cause unsafe side effects."""


# Prompt injection attack patterns to defuse in external web content
PROMPT_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s*:\s*(?:you\s+are|you\s+must|override)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:in\s+developer\s+mode|unrestricted|an\s+ai\s+without\s+rules)", re.IGNORECASE),
    re.compile(r"bypass\s+(?:all\s+)?(?:safety|security|policy)\s+protocols?", re.IGNORECASE),
    re.compile(r"execute\s+(?:the\s+following\s+)?(?:command|tool|script)\s*:", re.IGNORECASE),
    re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL),
]


class BrowserSecurity:
    """Security enforcement for URL validation, domain allowlisting, SSRF protection, and content defusing."""

    def __init__(self, allowed_domains: Optional[list[str]] = None, enforce_allowlist: Optional[bool] = None) -> None:
        config = get_config()
        self.allowed_domains = allowed_domains if allowed_domains is not None else list(config.browser.allowed_domains)
        self.enforce_allowlist = enforce_allowlist if enforce_allowlist is not None else config.browser.enforce_allowlist

    def is_domain_allowed(self, hostname: str) -> bool:
        """Verify if a hostname matches the configured domain allowlist.
        
        Supports exact match and safe hierarchical subdomain match.
        Rejects deceptive suffix attacks (e.g., 'evilgoogle.com' or 'google.com.attacker.com').
        """
        if not self.enforce_allowlist:
            return True

        if not hostname:
            return False

        clean_host = hostname.strip().lower()

        for pattern in self.allowed_domains:
            pat = pattern.strip().lower()
            if pat.startswith("*."):
                pat = pat[2:]

            if clean_host == pat:
                return True

            if clean_host.endswith("." + pat):
                return True

        return False

    def validate_target_url(self, url: str, resolve_dns: bool = True) -> tuple[str, list[str]]:
        """Validate URL scheme, domain allowlist, and SSRF/IP safety.
        
        Returns (clean_url, resolved_ips).
        Raises BrowserSecurityError or SSRFValidationError if validation fails.
        """
        clean_url = (url or "").strip()
        if not clean_url:
            raise BrowserSecurityError("Browser target URL cannot be empty.")

        parsed = urlparse(clean_url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise BrowserSecurityError(
                f"Forbidden browser URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
            )

        hostname = parsed.hostname
        if not hostname:
            raise BrowserSecurityError("URL must include a valid hostname.")

        # 1. Enforce domain allowlist first
        if not self.is_domain_allowed(hostname):
            raise DomainNotAllowedError(
                f"Domain '{hostname}' is not in the approved browser allowlist. Access denied."
            )

        # 2. Re-use central SSRF & DNS rebinding checks
        try:
            normalized_url, resolved_ips = validate_url(clean_url, resolve_dns=resolve_dns)
        except SSRFValidationError as s_err:
            raise BrowserSecurityError(f"SSRF Protection blocked URL: {s_err}") from s_err
        except SecurityError as sec_err:
            raise BrowserSecurityError(f"Security validation failed for URL: {sec_err}") from sec_err

        return normalized_url, resolved_ips

    def check_side_effect_allowed(self, action_name: str) -> None:
        """Block side-effect operations in read-only MVP."""
        lowered = action_name.lower().strip()
        blocked_actions = {
            "submit_form",
            "form_submit",
            "download_file",
            "download",
            "execute_script",
            "click_submit",
            "send_message",
            "purchase",
            "modify_account",
        }
        if any(b in lowered for b in blocked_actions):
            raise BrowserSideEffectBlockedError(
                f"Side-effect action '{action_name}' is disabled in read-only browser MVP."
            )

    def defuse_untrusted_content(self, text: str, url: str = "", title: str = "") -> str:
        """Defuse prompt injection attempts in webpage text and wrap in untrusted context."""
        cleaned = text or ""
        for pat in PROMPT_INJECTION_PATTERNS:
            cleaned = pat.sub("[REDACTED_UNTRUSTED_INSTRUCTION]", cleaned)

        escaped_title = title.replace('"', '&quot;')
        escaped_url = url.replace('"', '&quot;')

        return (
            f'<untrusted_web_context url="{escaped_url}" title="{escaped_title}">\n'
            f"{cleaned}\n"
            f"</untrusted_web_context>"
        )
