"""Typed exceptions for OLIVER 3.0 Backend API Client."""

from __future__ import annotations

from typing import Optional


class OLIVERClientError(Exception):
    """Base exception for all OLIVER desktop API client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class BackendConnectionError(OLIVERClientError):
    """Raised when the backend server is completely unreachable (connection refused, connect timeout).
    
    Safe for immediate local AI fallback because the request never reached the server.
    """
    pass


class AmbiguousTimeoutError(OLIVERClientError):
    """Raised when a request was sent to the server but the read timeout elapsed before completion.
    
    Must NOT trigger blind local AI fallback, as the backend may still be processing the request.
    """
    pass


class AuthenticationError(OLIVERClientError):
    """Raised when authentication fails (wrong password, invalid token, account disabled)."""
    pass


class TokenExpiredError(AuthenticationError):
    """Raised when refresh token has expired or been revoked; user must re-authenticate."""
    pass


class BackendRateLimitError(OLIVERClientError):
    """Raised when HTTP 429 Too Many Requests is returned by backend rate limiters."""
    pass


class BackendServerError(OLIVERClientError):
    """Raised when HTTP 5xx is returned by the central backend."""
    pass

