"""Authentication and token lifecycle manager for OLIVER Desktop Client."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

import httpx

from desktop.api_client.exceptions import (
    AuthenticationError,
    BackendConnectionError,
    BackendRateLimitError,
    BackendServerError,
    TokenExpiredError,
)
from desktop.api_client.token_store import WindowsCredentialStore

logger = logging.getLogger("oliver.api_client.auth")


class AuthManager:
    """Manages short-lived JWT access tokens and persistent refresh token rotation with thread safety."""

    def __init__(self, token_store: Optional[WindowsCredentialStore] = None) -> None:
        self.token_store = token_store or WindowsCredentialStore()
        self._refresh_lock = threading.RLock()
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._user_email: Optional[str] = None
        self._user_name: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """Return True if an access token or stored refresh token exists."""
        if self._access_token and time.time() < self._token_expires_at:
            return True
        if self._user_email and self.token_store.get_refresh_token(self._user_email):
            return True
        return False

    @property
    def user_email(self) -> Optional[str]:
        return self._user_email

    @property
    def user_name(self) -> Optional[str]:
        return self._user_name

    def set_session(self, email: str, access_token: str, expires_in: int, user_name: Optional[str] = None) -> None:
        """Update in-memory session details."""
        self._user_email = email.lower().strip()
        self._user_name = user_name
        self._access_token = access_token
        # Expire 30 seconds before actual deadline for safe clock drift margin
        self._token_expires_at = time.time() + max(10, expires_in - 30)

    def clear_session(self) -> None:
        """Purge all in-memory token state."""
        self._access_token = None
        self._token_expires_at = 0.0

    def login(self, client: httpx.Client, base_url: str, email: str, password: str) -> dict[str, Any]:
        """Authenticate with email and password via POST /api/auth/login."""
        clean_email = email.lower().strip()
        url = f"{base_url.rstrip('/')}/api/auth/login"

        try:
            resp = client.post(
                url,
                json={"email": clean_email, "password": password},
                headers={"Content-Type": "application/json"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise BackendConnectionError(f"Cannot connect to backend: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise BackendConnectionError(f"Backend connection timed out: {exc}") from exc

        if resp.status_code == 200:
            data = resp.json()
            access_token = data["access_token"]
            refresh_token = data["refresh_token"]
            expires_in = data.get("expires_in", 900)

            self.set_session(clean_email, access_token, expires_in)
            self.token_store.save_refresh_token(clean_email, refresh_token)
            logger.info("Login successful for user: %s", clean_email)
            return data
        elif resp.status_code == 401:
            raise AuthenticationError("Incorrect email or password.", status_code=401)
        elif resp.status_code == 403:
            raise AuthenticationError("This user account is inactive.", status_code=403)
        elif resp.status_code == 429:
            raise BackendRateLimitError("Too many login attempts. Please wait.", status_code=429)
        elif resp.status_code >= 500:
            raise BackendServerError(f"Backend error: {resp.text}", status_code=resp.status_code)
        else:
            raise AuthenticationError(f"Login failed: {resp.text}", status_code=resp.status_code)

    def refresh_tokens(self, client: httpx.Client, base_url: str, force: bool = False) -> str:
        """Perform thread-safe refresh token rotation using re-entrant mutex."""
        with self._refresh_lock:
            # Re-check inside lock: another thread might have just refreshed the token
            if not force and self._access_token and time.time() < self._token_expires_at:
                return self._access_token

            if not self._user_email:
                raise TokenExpiredError("No authenticated session available to refresh.")

            current_refresh = self.token_store.get_refresh_token(self._user_email)
            if not current_refresh:
                self.clear_session()
                raise TokenExpiredError("No refresh token available. Please log in again.")

            url = f"{base_url.rstrip('/')}/api/auth/refresh"
            try:
                resp = client.post(
                    url,
                    json={"refresh_token": current_refresh},
                    headers={"Content-Type": "application/json"},
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise BackendConnectionError(f"Cannot connect to backend during refresh: {exc}") from exc
            except httpx.TimeoutException as exc:
                raise BackendConnectionError(f"Backend timed out during token refresh: {exc}") from exc

            if resp.status_code == 200:
                data = resp.json()
                new_access = data["access_token"]
                new_refresh = data["refresh_token"]
                expires_in = data.get("expires_in", 900)

                self.set_session(self._user_email, new_access, expires_in)
                self.token_store.save_refresh_token(self._user_email, new_refresh)
                logger.debug("Successfully rotated tokens for: %s", self._user_email)
                return new_access
            elif resp.status_code in (401, 403):
                # Token revoked, expired, or reuse detected. Purge credentials.
                logger.warning("Refresh token rejected (%s). Clearing stored session.", resp.status_code)
                self.clear_session()
                if self._user_email:
                    self.token_store.delete_refresh_token(self._user_email)
                raise TokenExpiredError("Session expired or terminated. Please log in again.", status_code=resp.status_code)
            elif resp.status_code >= 500:
                raise BackendServerError(f"Backend error during refresh: {resp.text}", status_code=resp.status_code)
            else:
                raise AuthenticationError(f"Token refresh failed: {resp.text}", status_code=resp.status_code)

    def get_valid_access_token(self, client: httpx.Client, base_url: str) -> Optional[str]:
        """Return a valid access token, automatically refreshing if close to expiry."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        # Attempt refresh if email exists
        if self._user_email:
            try:
                return self.refresh_tokens(client, base_url)
            except TokenExpiredError:
                return None
            except BackendConnectionError:
                # If network is down, return current access token if not strictly expired
                if self._access_token and time.time() < (self._token_expires_at + 30):
                    return self._access_token
                raise

        return None

    def logout(self, client: httpx.Client, base_url: str) -> bool:
        """Revoke refresh token on backend and purge all stored credentials."""
        email = self._user_email
        refresh_token = self.token_store.get_refresh_token(email) if email else None

        if refresh_token:
            url = f"{base_url.rstrip('/')}/api/auth/logout"
            try:
                client.post(url, json={"refresh_token": refresh_token}, timeout=5.0)
            except Exception as exc:
                logger.debug("Logout remote revocation note: %s", exc)

        self.clear_session()
        if email:
            self.token_store.delete_refresh_token(email)
        self._user_email = None
        self._user_name = None
        logger.info("Logged out successfully.")
        return True
