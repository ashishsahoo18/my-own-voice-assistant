"""Central HTTP Client for OLIVER 3.0 Backend Integration."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import httpx

from desktop.api_client.auth import AuthManager
from desktop.api_client.exceptions import (
    AmbiguousTimeoutError,
    AuthenticationError,
    BackendConnectionError,
    BackendRateLimitError,
    BackendServerError,
    TokenExpiredError,
)

logger = logging.getLogger("oliver.api_client.client")


class OLIVERBackendClient:
    """Manages secure HTTP communication, authentication, error classification, and idempotency."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        auth_manager: Optional[AuthManager] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = auth_manager or AuthManager()
        self._custom_client = http_client is not None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=5.0,
                pool=5.0,
            )
        )

    def close(self) -> None:
        """Close the underlying HTTPX client connection pool."""
        if not self._custom_client:
            self._client.close()

    def check_health(self) -> tuple[bool, dict[str, Any]]:
        """Probe GET /api/health to verify backend connectivity."""
        url = f"{self.base_url}/api/health"
        try:
            resp = self._client.get(url, timeout=3.0)
            if resp.status_code == 200:
                return True, resp.json()
            return False, {"status_code": resp.status_code, "text": resp.text}
        except Exception as exc:
            return False, {"error": str(exc)}

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Authenticate user with email and password."""
        return self.auth.login(self._client, self.base_url, email, password)

    def logout(self) -> bool:
        """Log out the current user session."""
        return self.auth.logout(self._client, self.base_url)

    def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send chat message with client-generated idempotency request_id.
        
        Triages errors strictly:
        - ConnectError: Backend down -> raises BackendConnectionError (safe for local fallback)
        - ReadTimeout: In-flight execution -> raises AmbiguousTimeoutError (never blind fallback)
        - 401 Unauthorized: Transparently refreshes token and retries once
        """
        token = self.auth.get_valid_access_token(self._client, self.base_url)
        if not token:
            raise AuthenticationError("User is not authenticated. Please log in.", status_code=401)

        req_id = request_id or str(uuid.uuid4())
        url = f"{self.base_url}/api/chat"
        payload = {
            "message": message,
            "conversation_id": conversation_id,
            "request_id": req_id,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Request-ID": req_id,
            "Content-Type": "application/json",
        }

        # First attempt
        try:
            resp = self._send_chat_request(url, payload, headers)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise BackendConnectionError(f"Backend connection refused: {exc}") from exc
        except httpx.ReadTimeout as exc:
            raise AmbiguousTimeoutError(
                f"Backend chat generation timed out after request was sent (request_id={req_id})."
            ) from exc

        # Handle 401 retry with fresh token
        if resp.status_code == 401:
            logger.info("Received 401 on /api/chat. Attempting transparent token refresh...")
            try:
                new_token = self.auth.refresh_tokens(self._client, self.base_url, force=True)
                headers["Authorization"] = f"Bearer {new_token}"
                resp = self._send_chat_request(url, payload, headers)
            except TokenExpiredError:
                raise
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise BackendConnectionError(f"Backend connection lost during refresh: {exc}") from exc
            except httpx.ReadTimeout as exc:
                raise AmbiguousTimeoutError(f"Chat retry timed out (request_id={req_id}).") from exc

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            raise AuthenticationError("Authentication failed after token refresh.", status_code=401)
        elif resp.status_code == 403:
            raise AuthenticationError("Access forbidden: account inactive or unauthorized.", status_code=403)
        elif resp.status_code == 404:
            raise OLIVERClientError("Conversation not found or access denied.", status_code=404)
        elif resp.status_code == 429:
            raise BackendRateLimitError("Chat rate limit exceeded. Please wait a moment.", status_code=429)
        elif resp.status_code >= 500:
            raise BackendServerError(f"Backend chat error: {resp.text}", status_code=resp.status_code)
        else:
            raise OLIVERClientError(f"Unexpected chat response: {resp.text}", status_code=resp.status_code)

    def _send_chat_request(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        """Internal helper for executing POST /api/chat."""
        return self._client.post(url, json=payload, headers=headers)

    def reconcile_conversation(
        self,
        conversation_id: Optional[str],
        request_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Query GET /api/conversations/{id}/messages to verify whether an in-flight prompt was answered."""
        if not conversation_id:
            return None

        token = self.auth.get_valid_access_token(self._client, self.base_url)
        if not token:
            return None

        url = f"{self.base_url}/api/conversations/{conversation_id}/messages"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = self._client.get(url, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("messages", [])
                if messages and messages[-1].get("role") == "assistant":
                    # Last recorded message is from assistant
                    return messages[-1]
            return None
        except Exception as exc:
            logger.warning("Reconciliation query failed: %s", exc)
            return None

    def get_conversations(self) -> list[dict[str, Any]]:
        """List conversations for authenticated user."""
        token = self.auth.get_valid_access_token(self._client, self.base_url)
        if not token:
            raise AuthenticationError("User is not authenticated.", status_code=401)

        url = f"{self.base_url}/api/conversations"
        headers = {"Authorization": f"Bearer {token}"}
        resp = self._client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        raise OLIVERClientError(f"Failed to fetch conversations: {resp.text}", status_code=resp.status_code)
