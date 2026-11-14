"""URL Trust Classification and Accidental Website-Open Protection (Stage 2C).

Provides conservative URL validation, risk assessment, and domain classification
for OLIVER 3.0. Prevents accidental or misrecognized URL navigation through
voice or typed commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import ipaddress
import re
from typing import Optional, Set
import urllib.parse


class URLTrustLevel(Enum):
    """Trust levels for destination URLs."""

    TRUSTED = "trusted"                 # Pre-approved/alias destination, open immediately
    NEEDS_CONFIRMATION = "confirm"      # Valid external destination, requires explicit confirmation
    BLOCKED = "blocked"                 # Unsafe/forbidden scheme, IP, credentials, etc. Fail closed.


@dataclass(frozen=True)
class URLTrustResult:
    """Detailed result of URL security evaluation."""

    level: URLTrustLevel
    url: str
    display_host: str
    reason: str
    risk_factors: list[str] = field(default_factory=list)
    is_safe_to_open: bool = False


# Canonical trusted root domains derived from BrowserCommands.sites
# Any subdomain of these (e.g., mail.google.com, docs.google.com) is trusted.
DEFAULT_TRUSTED_ROOT_DOMAINS: frozenset[str] = frozenset({
    "google.com",
    "youtube.com",
    "github.com",
    "stackoverflow.com",
    "linkedin.com",
    "chatgpt.com",
    "gemini.google.com",
    "whatsapp.com",
    "instagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "flipkart.com",
    "amazon.in",
    "wikipedia.org",
    "reddit.com",
})

# Exact hostnames that are trusted but should NOT have wildcard subdomain trust
# (e.g. shared hosting / PaaS platforms where untrusted users can create subdomains)
DEFAULT_TRUSTED_EXACT_HOSTNAMES: frozenset[str] = frozenset({
    "ashishsahoo.vercel.app",
})

# Strictly prohibited URL schemes
BLOCKED_SCHEMES: frozenset[str] = frozenset({
    "javascript",
    "data",
    "file",
    "ftp",
    "ftps",
    "vbscript",
    "about",
    "blob",
    "chrome",
    "edge",
    "content",
    "ws",
    "wss",
})

# Suspicious lookalike patterns for voice misrecognitions and typosquatting
LOOKALIKE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:giithub|githhub|git-hub|githb)\.com$", re.IGNORECASE), "github.com"),
    (re.compile(r"^(?:g00gle|googl|gooogle|gogle)\.com$", re.IGNORECASE), "google.com"),
    (re.compile(r"^(?:youtub|you-tube|yootube|yuotube)\.com$", re.IGNORECASE), "youtube.com"),
    (re.compile(r"^(?:faceb00k|facbook|fecebook)\.com$", re.IGNORECASE), "facebook.com"),
    (re.compile(r"^(?:amazn|amzon|amazom)\.(?:com|in)$", re.IGNORECASE), "amazon.in"),
    (re.compile(r"^(?:wikipdia|wikpedia)\.org$", re.IGNORECASE), "wikipedia.org"),
    (re.compile(r"^(?:linkdin|linkeldn)\.com$", re.IGNORECASE), "linkedin.com"),
]

# Localhost and internal reserved domain suffixes
RESTRICTED_INTERNAL_SUFFIXES: tuple[str, ...] = (
    ".local",
    ".localhost",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".onion",
    ".test",
    ".invalid",
    ".example",
)


def is_trusted_host(
    host: str,
    extra_trusted_roots: Optional[Set[str]] = None,
    extra_trusted_exact: Optional[Set[str]] = None,
) -> bool:
    """Check if a hostname is in the trusted domain hierarchy."""
    clean_host = (host or "").strip().lower()
    if not clean_host:
        return False

    # Strip trailing dot if present (FQDN)
    clean_host = clean_host.rstrip(".")

    # 1. Exact match check (including exact-only hosts like portfolio)
    exact_hosts = DEFAULT_TRUSTED_EXACT_HOSTNAMES
    if extra_trusted_exact:
        exact_hosts = exact_hosts | {h.strip().lower() for h in extra_trusted_exact}

    if clean_host in exact_hosts:
        return True

    # Also check if it's www.<exact_host>
    if clean_host.startswith("www.") and clean_host[4:] in exact_hosts:
        return True

    # 2. Hierarchical root domain check
    root_domains = DEFAULT_TRUSTED_ROOT_DOMAINS
    if extra_trusted_roots:
        root_domains = root_domains | {d.strip().lower() for d in extra_trusted_roots}

    for root in root_domains:
        if clean_host == root:
            return True
        if clean_host.endswith("." + root):
            return True

    return False


def classify_url(
    raw_url: str,
    extra_trusted_roots: Optional[Set[str]] = None,
    extra_trusted_exact: Optional[Set[str]] = None,
) -> URLTrustResult:
    """Conservatively evaluate and classify the trust and safety level of a URL.

    Returns a URLTrustResult with level TRUSTED, NEEDS_CONFIRMATION, or BLOCKED.
    """
    if not isinstance(raw_url, str):
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=str(raw_url),
            display_host="",
            reason="Invalid URL type. Target must be a non-empty string.",
            risk_factors=["invalid_type"],
        )

    clean_url = raw_url.strip()
    if not clean_url:
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=clean_url,
            display_host="",
            reason="Target URL cannot be empty.",
            risk_factors=["empty_target"],
        )

    # Detect URLs with unencoded spaces
    if " " in clean_url:
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=clean_url,
            display_host="",
            reason="URLs cannot contain whitespace.",
            risk_factors=["whitespace_in_url"],
        )

    # Check for early scheme indicator (e.g. javascript:, data:, file:)
    lower_input = clean_url.lower()
    for blocked_scheme in BLOCKED_SCHEMES:
        if lower_input.startswith(f"{blocked_scheme}:"):
            return URLTrustResult(
                level=URLTrustLevel.BLOCKED,
                url=clean_url,
                display_host="",
                reason=f"Scheme '{blocked_scheme}' is strictly prohibited for security.",
                risk_factors=[f"blocked_scheme_{blocked_scheme}"],
            )

    # Normalize missing scheme
    effective_url = clean_url
    if not effective_url.startswith(("http://", "https://")):
        effective_url = f"https://{effective_url}"

    # Parse URL
    try:
        parsed = urllib.parse.urlparse(effective_url)
    except Exception as exc:
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=clean_url,
            display_host="",
            reason=f"Malformed URL: {exc}",
            risk_factors=["parse_failure"],
        )

    # Validate scheme
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=effective_url,
            display_host="",
            reason=f"Unsupported scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.",
            risk_factors=["unsupported_scheme"],
        )

    # Embedded credentials check (e.g. http://user:pass@host)
    if parsed.username or parsed.password or ("@" in (parsed.netloc or "")):
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=effective_url,
            display_host=parsed.hostname or "",
            reason="URLs with embedded credentials are prohibited for security.",
            risk_factors=["embedded_credentials"],
        )

    # Hostname validation
    raw_host = parsed.hostname
    if not raw_host:
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=effective_url,
            display_host="",
            reason="URL must contain a valid domain or hostname.",
            risk_factors=["missing_hostname"],
        )

    host = raw_host.strip().lower().rstrip(".")
    risk_factors: list[str] = []

    # Check for localhost / loopback interfaces
    if host in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}:
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=effective_url,
            display_host=host,
            reason="Access to localhost and loopback interfaces is restricted.",
            risk_factors=["localhost_loopback"],
        )

    # Check restricted internal suffixes (.local, .internal, etc.)
    if any(host.endswith(suffix) for suffix in RESTRICTED_INTERNAL_SUFFIXES):
        return URLTrustResult(
            level=URLTrustLevel.BLOCKED,
            url=effective_url,
            display_host=host,
            reason=f"Access to private or local network domain '{host}' is restricted.",
            risk_factors=["private_network_suffix"],
        )

    # IP address literal validation
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        ):
            return URLTrustResult(
                level=URLTrustLevel.BLOCKED,
                url=effective_url,
                display_host=str(ip),
                reason=f"Access to private/restricted IP address '{ip}' is blocked by security policy.",
                risk_factors=["restricted_ip_literal"],
            )
        # Public IP literal — permitted only with confirmation
        risk_factors.append("public_ip_literal")
        return URLTrustResult(
            level=URLTrustLevel.NEEDS_CONFIRMATION,
            url=effective_url,
            display_host=str(ip),
            reason=f"Direct IP address destination '{ip}' requires explicit confirmation.",
            risk_factors=risk_factors,
            is_safe_to_open=False,
        )
    except ValueError:
        # Not an IP literal; continue domain name checks
        pass

    # Check for Internationalized Domain Names (Punycode / Homograph attacks)
    if "xn--" in host:
        risk_factors.append("punycode_idn")
    if any(ord(char) > 127 for char in host):
        risk_factors.append("unicode_homograph")

    if risk_factors:
        return URLTrustResult(
            level=URLTrustLevel.NEEDS_CONFIRMATION,
            url=effective_url,
            display_host=host,
            reason=(
                f"Internationalized domain name (IDN/Punycode: {host}) detected. "
                "Potential homograph risk — explicit confirmation required."
            ),
            risk_factors=risk_factors,
            is_safe_to_open=False,
        )

    # Check for suspicious lookalike / voice misrecognition patterns
    for pattern, target in LOOKALIKE_PATTERNS:
        if pattern.match(host):
            risk_factors.append(f"lookalike_{target}")
            return URLTrustResult(
                level=URLTrustLevel.NEEDS_CONFIRMATION,
                url=effective_url,
                display_host=host,
                reason=(
                    f"Possible voice recognition mistake or lookalike domain for '{target}'. "
                    f"Destination is '{host}' — confirmation required."
                ),
                risk_factors=risk_factors,
                is_safe_to_open=False,
            )

    # Check if host is pre-approved / trusted
    if is_trusted_host(host, extra_trusted_roots, extra_trusted_exact):
        return URLTrustResult(
            level=URLTrustLevel.TRUSTED,
            url=effective_url,
            display_host=host,
            reason=f"Trusted destination: {host}",
            risk_factors=[],
            is_safe_to_open=True,
        )

    # General external valid destination — requires explicit confirmation
    risk_factors.append("external_destination")
    return URLTrustResult(
        level=URLTrustLevel.NEEDS_CONFIRMATION,
        url=effective_url,
        display_host=host,
        reason=f"External destination '{host}' is not in the trusted list and requires confirmation.",
        risk_factors=risk_factors,
        is_safe_to_open=False,
    )

