"""OLIVER 3.0 Desktop API Client package."""

from desktop.api_client.auth import AuthManager
from desktop.api_client.client import OLIVERBackendClient
from desktop.api_client.exceptions import (
    AmbiguousTimeoutError,
    AuthenticationError,
    BackendConnectionError,
    BackendRateLimitError,
    BackendServerError,
    OLIVERClientError,
    TokenExpiredError,
)
from desktop.api_client.token_store import WindowsCredentialStore

__all__ = [
    "OLIVERBackendClient",
    "AuthManager",
    "WindowsCredentialStore",
    "OLIVERClientError",
    "BackendConnectionError",
    "AmbiguousTimeoutError",
    "AuthenticationError",
    "TokenExpiredError",
    "BackendRateLimitError",
    "BackendServerError",
]

