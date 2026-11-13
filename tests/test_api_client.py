"""Unit and integration tests for OLIVER 3.0 Desktop API Client (15-Scenario Matrix)."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import httpx

from core.config import OliverConfig, get_config
from desktop.api_client.auth import AuthManager
from desktop.api_client.client import OLIVERBackendClient
from desktop.api_client.exceptions import (
    AmbiguousTimeoutError,
    AuthenticationError,
    BackendConnectionError,
    BackendRateLimitError,
    OLIVERClientError,
    TokenExpiredError,
)
from desktop.api_client.token_store import WindowsCredentialStore


class InMemoryTestTokenStore(WindowsCredentialStore):
    """Isolated in-memory token store for test repeatability."""

    def __init__(self) -> None:
        super().__init__(service_name="OLIVER_TEST_SUITE")
        self._keyring_available = False
        self._store: dict[str, str] = {}

    def save_refresh_token(self, email: str, refresh_token: str) -> bool:
        self._store[email.lower().strip()] = refresh_token
        return True

    def get_refresh_token(self, email: str) -> str | None:
        return self._store.get(email.lower().strip())

    def delete_refresh_token(self, email: str) -> bool:
        return self._store.pop(email.lower().strip(), None) is not None


class TestOLIVERBackendClientMatrix(unittest.TestCase):
    """15-Point Regression Test Suite for Desktop-Backend Integration."""

    def setUp(self) -> None:
        self.token_store = InMemoryTestTokenStore()
        self.auth_manager = AuthManager(token_store=self.token_store)

    # -------------------------------------------------------------------------
    # Scenario 1: Local Mode Default
    # -------------------------------------------------------------------------
    def test_01_local_mode_default(self) -> None:
        cfg = get_config()
        self.assertEqual(cfg.backend.backend_mode, "local")
        self.assertTrue(cfg.backend.auto_fallback_local)

    # -------------------------------------------------------------------------
    # Scenario 2: Backend Mode Configuration
    # -------------------------------------------------------------------------
    def test_02_backend_mode_configured(self) -> None:
        with patch.dict("os.environ", {"BACKEND_MODE": "backend", "BACKEND_URL": "http://192.168.1.50:8000"}):
            from core.config import reload_config
            cfg = reload_config()
            self.assertEqual(cfg.backend.backend_mode, "backend")
            self.assertEqual(cfg.backend.backend_url, "http://192.168.1.50:8000")
            # Restore
            reload_config()

    # -------------------------------------------------------------------------
    # Scenario 3: Login Success
    # -------------------------------------------------------------------------
    def test_03_login_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "mock-access-jwt-123",
                        "refresh_token": "mock-refresh-hex-456",
                        "token_type": "bearer",
                        "expires_in": 900,
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        data = client.login("test@example.com", "secretPassword123")
        self.assertEqual(data["access_token"], "mock-access-jwt-123")
        self.assertTrue(self.auth_manager.is_authenticated)
        self.assertEqual(self.token_store.get_refresh_token("test@example.com"), "mock-refresh-hex-456")

    # -------------------------------------------------------------------------
    # Scenario 4: Invalid Password Rejection (401)
    # -------------------------------------------------------------------------
    def test_04_invalid_credentials_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "Incorrect email or password."})

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        with self.assertRaises(AuthenticationError) as ctx:
            client.login("test@example.com", "wrongPassword")
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertFalse(self.auth_manager.is_authenticated)
        self.assertIsNone(self.token_store.get_refresh_token("test@example.com"))

    # -------------------------------------------------------------------------
    # Scenario 5: Inactive Account Rejection (403)
    # -------------------------------------------------------------------------
    def test_05_inactive_account_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"detail": "This user account is inactive."})

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        with self.assertRaises(AuthenticationError) as ctx:
            client.login("disabled@example.com", "password123")
        self.assertEqual(ctx.exception.status_code, 403)

    # -------------------------------------------------------------------------
    # Scenario 6: Backend Chat Success with Idempotency request_id
    # -------------------------------------------------------------------------
    def test_06_backend_chat_success_with_request_id(self) -> None:
        received_requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                received_requests.append(request)
                return httpx.Response(
                    200,
                    json={
                        "conversation_id": "conv-uuid-1",
                        "reply": "Hello from backend Ollama!",
                        "latency_ms": 1250.5,
                        "model": "ollama/llama3.2",
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager.set_session("user@example.com", "valid-jwt", expires_in=900)
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        resp = client.chat("What is the speed of light?", request_id="custom-req-123")
        self.assertEqual(resp["reply"], "Hello from backend Ollama!")
        self.assertEqual(resp["conversation_id"], "conv-uuid-1")
        self.assertEqual(len(received_requests), 1)
        # Verify request_id attached in payload and header
        self.assertEqual(received_requests[0].headers["X-Request-ID"], "custom-req-123")
        self.assertIn("custom-req-123", received_requests[0].content.decode())

    # -------------------------------------------------------------------------
    # Scenario 7: Connection Refusal Triggers BackendConnectionError
    # -------------------------------------------------------------------------
    def test_07_connection_refusal_raises_connection_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused to 127.0.0.1:8000")

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager.set_session("user@example.com", "valid-jwt", expires_in=900)
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        with self.assertRaises(BackendConnectionError) as ctx:
            client.chat("Hello?")
        self.assertIn("refused", str(ctx.exception).lower())

    # -------------------------------------------------------------------------
    # Scenario 8: In-Flight Read Timeout Triggers AmbiguousTimeoutError (NOT ConnectError)
    # -------------------------------------------------------------------------
    def test_08_read_timeout_raises_ambiguous_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Server took longer than 30s to respond")

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager.set_session("user@example.com", "valid-jwt", expires_in=900)
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        # Must raise AmbiguousTimeoutError, NEVER BackendConnectionError
        with self.assertRaises(AmbiguousTimeoutError):
            client.chat("Complex prompt taking 45s", request_id="timeout-id-99")

    # -------------------------------------------------------------------------
    # Scenario 9: Chat Idempotency in Backend ChatService
    # -------------------------------------------------------------------------
    def test_09_backend_chat_service_idempotency(self) -> None:
        import asyncio
        from backend.app.schemas.chat import ChatRequest
        from backend.app.services.chat_service import ChatService
        import backend.app.services.chat_service as cs
        from backend.app.services.ai_provider import AIProvider
        from backend.app.models.user import User

        class DeterministicAIProvider(AIProvider):
            def __init__(self):
                self.call_count = 0

            async def generate_response(self, prompt: str, system_prompt: str = "") -> tuple[str, float]:
                self.call_count += 1
                return f"Echo answer: {prompt}", 25.0

            async def check_health(self) -> tuple[bool, str, str]:
                return True, "mock-llama3.2", ""

        mock_provider = DeterministicAIProvider()
        original_provider = cs.ai_provider
        cs.ai_provider = mock_provider

        try:
            ChatService.clear_idempotency_cache()
            mock_db = MagicMock()
            mock_user = User(id="user-123", email="user@example.com", full_name="Test User")
            req = ChatRequest(message="Echo test", request_id=f"idemp-{time.time()}")

            async def run_test():
                res1 = await ChatService.process_chat(mock_db, mock_user, req)
                res2 = await ChatService.process_chat(mock_db, mock_user, req)
                self.assertEqual(res1.reply, res2.reply)
                self.assertEqual(res1.reply, "Echo answer: Echo test")
                # Idempotency guarantee: AI provider was invoked ONLY ONCE despite 2 calls
                self.assertEqual(mock_provider.call_count, 1)

            asyncio.run(run_test())
        finally:
            cs.ai_provider = original_provider

    # -------------------------------------------------------------------------
    # Scenario 10: Transparent Token Refresh
    # -------------------------------------------------------------------------
    def test_10_transparent_token_refresh(self) -> None:
        call_count = {"chat": 0, "refresh": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/chat":
                call_count["chat"] += 1
                auth_header = request.headers.get("Authorization", "")
                if "fresh-token-abc" in auth_header:
                    return httpx.Response(200, json={"conversation_id": "c1", "reply": "Success!", "latency_ms": 100, "model": "m"})
                return httpx.Response(401, json={"detail": "Token expired"})
            elif request.url.path == "/api/auth/refresh":
                call_count["refresh"] += 1
                return httpx.Response(
                    200,
                    json={
                        "access_token": "fresh-token-abc",
                        "refresh_token": "new-refresh-xyz",
                        "token_type": "bearer",
                        "expires_in": 900,
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager.set_session("user@example.com", "expired-token", expires_in=900)
        self.token_store.save_refresh_token("user@example.com", "existing-refresh")
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        resp = client.chat("Test question")
        self.assertEqual(resp["reply"], "Success!")
        self.assertEqual(call_count["refresh"], 1)
        self.assertEqual(call_count["chat"], 2)  # Initial 401 + retry 200

    # -------------------------------------------------------------------------
    # Scenario 11: Concurrent Refresh Serialization under Mutex
    # -------------------------------------------------------------------------
    def test_11_concurrent_refresh_serialization(self) -> None:
        refresh_calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/refresh":
                refresh_calls.append(time.time())
                time.sleep(0.05)
                return httpx.Response(
                    200,
                    json={
                        "access_token": "concurrent-fresh-jwt",
                        "refresh_token": "rotated-refresh",
                        "token_type": "bearer",
                        "expires_in": 900,
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager._user_email = "concurrent@example.com"
        self.token_store.save_refresh_token("concurrent@example.com", "refresh-token")

        results = []

        def worker():
            token = self.auth_manager.refresh_tokens(mock_http, "http://127.0.0.1:8000")
            results.append(token)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], "concurrent-fresh-jwt")
        self.assertEqual(results[1], "concurrent-fresh-jwt")
        # Due to RLock and re-check, only ONE network refresh was executed!
        self.assertEqual(len(refresh_calls), 1)

    # -------------------------------------------------------------------------
    # Scenario 12: Revoked Refresh Token Recovery
    # -------------------------------------------------------------------------
    def test_12_revoked_token_purges_session(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/refresh":
                return httpx.Response(401, json={"detail": "Refresh token reuse detected."})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager._user_email = "revoked@example.com"
        self.token_store.save_refresh_token("revoked@example.com", "bad-token")

        with self.assertRaises(TokenExpiredError):
            self.auth_manager.refresh_tokens(mock_http, "http://127.0.0.1:8000")

        # Credentials must be wiped
        self.assertFalse(self.auth_manager.is_authenticated)
        self.assertIsNone(self.token_store.get_refresh_token("revoked@example.com"))

    # -------------------------------------------------------------------------
    # Scenario 13: Logout Credential Purge
    # -------------------------------------------------------------------------
    def test_13_logout_purges_all_credentials(self) -> None:
        logout_called = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/logout":
                logout_called.append(True)
                return httpx.Response(200, json={"message": "Logged out successfully."})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager.set_session("user@example.com", "jwt-to-logout", expires_in=900)
        self.token_store.save_refresh_token("user@example.com", "refresh-to-logout")
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        client.logout()
        self.assertTrue(len(logout_called) > 0)
        self.assertFalse(self.auth_manager.is_authenticated)
        self.assertIsNone(self.token_store.get_refresh_token("user@example.com"))

    # -------------------------------------------------------------------------
    # Scenario 14: Reconciliation Query Protocol
    # -------------------------------------------------------------------------
    def test_14_reconciliation_protocol(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/conversations/conv-123/messages":
                return httpx.Response(
                    200,
                    json={
                        "id": "conv-123",
                        "title": "Chat",
                        "created_at": "2026-11-07T00:00:00Z",
                        "updated_at": "2026-11-07T00:00:00Z",
                        "messages": [
                            {"id": "m1", "role": "user", "content": "Question?", "created_at": "2026-11-07T00:00:00Z"},
                            {"id": "m2", "role": "assistant", "content": "Reconciled Answer!", "created_at": "2026-11-07T00:00:05Z"},
                        ],
                    },
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        mock_http = httpx.Client(transport=transport)
        self.auth_manager.set_session("user@example.com", "valid-jwt", expires_in=900)
        client = OLIVERBackendClient(auth_manager=self.auth_manager, http_client=mock_http)

        reconciled = client.reconcile_conversation("conv-123")
        self.assertIsNotNone(reconciled)
        self.assertEqual(reconciled["role"], "assistant")
        self.assertEqual(reconciled["content"], "Reconciled Answer!")

    # -------------------------------------------------------------------------
    # Scenario 15: Secret Redaction
    # -------------------------------------------------------------------------
    def test_15_secret_redaction(self) -> None:
        self.auth_manager.set_session("sensitive@example.com", "SUPER-SECRET-ACCESS-JWT-999", expires_in=900)
        client = OLIVERBackendClient(auth_manager=self.auth_manager)
        client_repr = repr(client)
        auth_repr = repr(self.auth_manager)

        # Neither repr should expose raw JWT
        self.assertNotIn("SUPER-SECRET-ACCESS-JWT-999", client_repr)
        self.assertNotIn("SUPER-SECRET-ACCESS-JWT-999", auth_repr)


if __name__ == "__main__":
    unittest.main()
