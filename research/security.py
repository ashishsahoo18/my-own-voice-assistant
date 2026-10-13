"""Security and SSRF protection for OLIVER 2.0 web research."""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse, urljoin
from typing import Optional, Set

import requests

logger = logging.getLogger("oliver.research.security")


class SecurityError(RuntimeError):
    """Base exception for research security violations."""


class SSRFValidationError(SecurityError):
    """Raised when a URL targets restricted internal, private, or loopback networks."""


class UnsupportedContentTypeError(SecurityError):
    """Raised when a fetched resource is not a safe text or document format."""


class ResponseTooLargeError(SecurityError):
    """Raised when a remote payload exceeds maximum safe memory/size thresholds."""


class RequestTimeoutError(SecurityError):
    """Raised when an outbound HTTP request exceeds timeout limits."""


# Restricted IPv4 and IPv6 networks
BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # IPv4 Private / Loopback / Link-Local / Reserved
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),       # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-Local (AWS/cloud metadata)
    ipaddress.ip_network("172.16.0.0/12"),      # Private
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),     # 6to4 Relay Anycast
    ipaddress.ip_network("192.168.0.0/16"),     # Private
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved / Future use
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6 Loopback / Link-Local / Unique-Local / Multicast
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::1/128"),           # Loopback
    ipaddress.ip_network("100::/64"),          # Discard prefix
    ipaddress.ip_network("fc00::/7"),          # Unique local (ULA)
    ipaddress.ip_network("fe80::/10"),         # Link-local unicast
    ipaddress.ip_network("ff00::/8"),          # Multicast
]

ALLOWED_SCHEMES: Set[str] = {"http", "https"}
ALLOWED_CONTENT_TYPES: Set[str] = {
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
    "text/xml",
    "application/xhtml+xml",
}


def is_ip_restricted(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if IP is private, loopback, link-local, multicast, or reserved."""
    # Check mapped IPv4 in IPv6 (e.g., ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    # Check RFC 6052 Well-Known Prefix 64:ff9b::/96 (NAT64 IPv4-IPv6 translation)
    if isinstance(ip, ipaddress.IPv6Address) and ip in ipaddress.ip_network("64:ff9b::/96"):
        embedded_v4 = ipaddress.IPv4Address(ip.packed[-4:])
        return is_ip_restricted(embedded_v4)

    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True

    for net in BLOCKED_NETWORKS:
        if isinstance(ip, (ipaddress.IPv4Address, ipaddress.IPv6Address)) and ip in net:
            return True

    return False


def validate_url(url: str, resolve_dns: bool = True) -> tuple[str, list[str]]:
    """Validate URL scheme and resolve destination IPs to prevent SSRF and DNS rebinding.
    
    Returns (normalized_url, resolved_ip_list).
    Raises SSRFValidationError if destination targets internal, private, or loopback network.
    """
    clean_url = (url or "").strip()
    if not clean_url:
        raise SSRFValidationError("URL cannot be empty.")

    parsed = urlparse(clean_url)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SSRFValidationError(f"Forbidden URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL must include a valid hostname.")

    clean_host = hostname.lower().strip("[]")
    
    # Block immediate text localhost aliases
    if clean_host in {"localhost", "localhost.localdomain", "0.0.0.0", "127.0.0.1", "::1"}:
        raise SSRFValidationError(f"Target '{hostname}' is a forbidden local destination.")

    resolved_ips: list[str] = []

    # If host is already an IP address literal, validate immediately
    try:
        raw_ip_obj = ipaddress.ip_address(clean_host)
        if is_ip_restricted(raw_ip_obj):
            raise SSRFValidationError(
                f"SSRF Protection: Host '{hostname}' is a restricted IP address."
            )
        resolved_ips.append(str(raw_ip_obj))
    except ValueError:
        pass

    if resolve_dns:
        try:
            # Resolve both IPv4 and IPv6 addresses
            addr_info = socket.getaddrinfo(clean_host, parsed.port or (443 if scheme == "https" else 80))
            for family, socktype, proto, canonname, sockaddr in addr_info:
                ip_str = sockaddr[0]
                if ip_str not in resolved_ips:
                    resolved_ips.append(ip_str)
        except socket.gaierror as exc:
            raise SSRFValidationError(f"DNS resolution failed for hostname '{hostname}': {exc}") from exc

        if not resolved_ips:
            raise SSRFValidationError(f"No IP addresses resolved for hostname '{hostname}'.")

        for ip_str in resolved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if is_ip_restricted(ip_obj):
                    logger.warning("SSRF blocked: '%s' resolved to restricted IP '%s'", hostname, ip_str)
                    raise SSRFValidationError(
                        f"SSRF Protection: Hostname '{hostname}' resolves to restricted IP address '{ip_str}'."
                    )
            except ValueError as exc:
                raise SSRFValidationError(f"Invalid IP address format resolved '{ip_str}': {exc}") from exc

    return clean_url, resolved_ips


class SafeHTTPClient:
    """Hardened HTTP client with per-redirect SSRF revalidation, timeout bounds, and size limits."""

    def __init__(
        self,
        connect_timeout: float = 3.0,
        read_timeout: float = 5.0,
        max_bytes: int = 50_000,
        max_redirects: int = 3,
        user_agent: str = "OLIVER-AI-ResearchBot/2.0 (+https://github.com/ashishsahoo18)",
    ) -> None:
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent

    def get(self, url: str) -> tuple[str, str, dict[str, str]]:
        """Fetch URL with SSRF protection, size limits, and revalidated redirects.
        
        Returns (content_text, final_url, headers).
        """
        current_url = url
        redirect_count = 0

        while True:
            # 1. Validate destination and resolve DNS before opening socket
            validated_url, _ = validate_url(current_url, resolve_dns=True)

            try:
                # Disable automatic requests redirection to inspect each step manually
                response = requests.get(
                    validated_url,
                    headers={"User-Agent": self.user_agent},
                    timeout=(self.connect_timeout, self.read_timeout),
                    allow_redirects=False,
                    stream=True,
                )
            except requests.Timeout as exc:
                raise RequestTimeoutError(f"Request timed out fetching {validated_url}: {exc}") from exc
            except requests.RequestException as exc:
                raise SecurityError(f"HTTP request failed fetching {validated_url}: {exc}") from exc

            # 2. Handle HTTP Redirection safely
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                if redirect_count > self.max_redirects:
                    response.close()
                    raise SecurityError(f"Exceeded maximum redirect limit of {self.max_redirects}.")

                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise SecurityError(f"Redirect response {response.status_code} missing Location header.")

                # Resolve relative redirect URLs against the base URL
                next_url = urljoin(current_url, location)
                logger.info("Following redirect (%d/%d): %s -> %s", redirect_count, self.max_redirects, current_url, next_url)
                current_url = next_url
                continue

            # 3. Check Content-Type
            content_type_header = response.headers.get("Content-Type", "")
            mime_type = content_type_header.split(";")[0].strip().lower()

            if mime_type and not any(allowed in mime_type for allowed in ALLOWED_CONTENT_TYPES):
                response.close()
                raise UnsupportedContentTypeError(
                    f"Forbidden content type '{mime_type}'. Only safe text/document types are allowed."
                )

            # 4. Check Content-Length header if provided
            content_length = response.headers.get("Content-Length")
            if content_length and content_length.isdigit():
                if int(content_length) > self.max_bytes:
                    response.close()
                    raise ResponseTooLargeError(
                        f"Response payload {content_length} bytes exceeds maximum safe limit of {self.max_bytes} bytes."
                    )

            # 5. Stream body with hard byte-limit enforcement
            body_bytes = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                body_bytes.extend(chunk)
                if len(body_bytes) > self.max_bytes:
                    response.close()
                    raise ResponseTooLargeError(
                        f"Response body exceeded maximum limit of {self.max_bytes} bytes while streaming."
                    )

            encoding = response.encoding or "utf-8"
            try:
                text_content = body_bytes.decode(encoding, errors="replace")
            except Exception:
                text_content = body_bytes.decode("utf-8", errors="replace")

            response.close()
            headers_dict = dict(response.headers)
            return text_content, validated_url, headers_dict
