"""Secure token storage via native Windows Credential Manager (DPAPI).

Guarantees that rotating refresh tokens are never written to plaintext .env,
config JSON files, or SQLite databases.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("oliver.api_client.token_store")

SERVICE_NAME = "OLIVER_AI_ASSISTANT"


class WindowsCredentialStore:
    """Manages persistent secure storage of credentials using Windows Credential Manager."""

    def __init__(self, service_name: str = SERVICE_NAME) -> None:
        self.service_name = service_name
        self._in_memory_fallback: dict[str, str] = {}
        self._keyring_available = self._probe_keyring()

    def _probe_keyring(self) -> bool:
        """Check whether keyring is importable and functional."""
        try:
            import keyring
            backend = keyring.get_keyring()
            logger.info("Keyring initialized with backend: %s", type(backend).__name__)
            return True
        except Exception as exc:
            logger.warning("Keyring unavailable (%s). Falling back to session memory storage.", exc)
            return False

    def save_refresh_token(self, email: str, refresh_token: str) -> bool:
        """Save refresh token securely into Windows Credential Manager."""
        if not email or not refresh_token:
            return False

        if self._keyring_available:
            try:
                import keyring
                keyring.set_password(self.service_name, email.lower().strip(), refresh_token)
                return True
            except Exception as exc:
                logger.error("Failed to write to Windows Credential Manager: %s. Using session fallback.", exc)

        # Fallback to in-memory session only (never disk)
        self._in_memory_fallback[email.lower().strip()] = refresh_token
        return True

    def get_refresh_token(self, email: str) -> Optional[str]:
        """Retrieve refresh token from Windows Credential Manager or session fallback."""
        if not email:
            return None

        clean_email = email.lower().strip()

        if self._keyring_available:
            try:
                import keyring
                token = keyring.get_password(self.service_name, clean_email)
                if token:
                    return token
            except Exception as exc:
                logger.warning("Failed to read from Windows Credential Manager: %s", exc)

        return self._in_memory_fallback.get(clean_email)

    def delete_refresh_token(self, email: str) -> bool:
        """Delete refresh token from Windows Credential Manager upon logout."""
        if not email:
            return False

        clean_email = email.lower().strip()
        deleted = False

        if self._keyring_available:
            try:
                import keyring
                keyring.delete_password(self.service_name, clean_email)
                deleted = True
            except Exception as exc:
                logger.debug("Keyring delete_password note: %s", exc)

        if clean_email in self._in_memory_fallback:
            del self._in_memory_fallback[clean_email]
            deleted = True

        return deleted

