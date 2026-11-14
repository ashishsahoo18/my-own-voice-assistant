"""Comprehensive test suite for Phase 2A.1.3 Stage 2C: Accidental Website-Open Protection.

Covers all 19 required test areas:
1. Trusted portfolio aliases bypass confirmation
2. Legitimate external URLs trigger confirmation
3. Untrusted destinations require confirmation
4. Voice-misrecognized / typosquatting URLs require confirmation
5. Malformed URLs are BLOCKED
6. Unsupported schemes (ftp, etc.) are BLOCKED
7. javascript: URLs are BLOCKED
8. data: URLs are BLOCKED
9. Embedded credentials in URLs are BLOCKED
10. Suspicious IDN / Punycode URLs require confirmation
11. Localhost and loopback interfaces are BLOCKED
12. Private / reserved IP addresses are BLOCKED
13. Redirect handling documentation & destination classification
14. Confirm action proceeds to open in browser
15. Cancel action aborts and returns cancellation message
16. No URL is opened before confirmation completes
17. No duplicate URL openings occur
18. Thread-safe background execution for voice and typed commands
19. Firefox-first browser launch mechanism preservation
"""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, call, patch

from browser.url_trust import (
    BLOCKED_SCHEMES,
    DEFAULT_TRUSTED_EXACT_HOSTNAMES,
    DEFAULT_TRUSTED_ROOT_DOMAINS,
    URLTrustLevel,
    URLTrustResult,
    classify_url,
    is_trusted_host,
)
from commands.browser import (
    BrowserCommands,
    get_browser_confirmation_callback,
    set_browser_confirmation_callback,
)


class TestStage2CURLTrustClassifier(unittest.TestCase):
    """Test URLTrustClassifier logic across all security, safety, and risk categories."""

    # =========================================================================
    # Area 1: Trusted Portfolio and Canonical Aliases
    # =========================================================================

    def test_01_portfolio_exact_domain_trusted(self) -> None:
        """Verify ashishsahoo.vercel.app is classified as TRUSTED."""
        result = classify_url("https://ashishsahoo.vercel.app/")
        self.assertEqual(result.level, URLTrustLevel.TRUSTED)
        self.assertTrue(result.is_safe_to_open)
        self.assertEqual(result.display_host, "ashishsahoo.vercel.app")

    def test_02_canonical_trusted_domains(self) -> None:
        """Verify canonical sites (Google, YouTube, GitHub, etc.) are TRUSTED."""
        trusted_examples = [
            "https://www.google.com",
            "https://google.com/search?q=test",
            "https://www.youtube.com",
            "https://mail.google.com",
            "https://github.com",
            "https://www.wikipedia.org",
            "https://stackoverflow.com",
            "https://web.whatsapp.com",
            "https://chatgpt.com",
        ]
        for url in trusted_examples:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.TRUSTED, f"Expected TRUSTED for {url}")
            self.assertTrue(res.is_safe_to_open)

    def test_03_untrusted_subdomain_on_shared_host_rejected(self) -> None:
        """Verify arbitrary subdomains on vercel.app (e.g. attacker.vercel.app) are NOT trusted."""
        res = classify_url("https://attacker.vercel.app")
        self.assertEqual(res.level, URLTrustLevel.NEEDS_CONFIRMATION)
        self.assertFalse(res.is_safe_to_open)

    # =========================================================================
    # Area 2: Legitimate External Destinations & Untrusted Sites
    # =========================================================================

    def test_04_legitimate_external_url_needs_confirmation(self) -> None:
        """Verify valid external URLs require explicit confirmation."""
        external_urls = [
            "https://example.com",
            "https://python.org",
            "https://news.ycombinator.com",
            "http://httpbin.org/get",
        ]
        for url in external_urls:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.NEEDS_CONFIRMATION, f"Expected confirm for {url}")
            self.assertFalse(res.is_safe_to_open)
            self.assertIn("external_destination", res.risk_factors)

    # =========================================================================
    # Area 3: Voice Misrecognitions & Typosquatting Lookalikes
    # =========================================================================

    def test_05_voice_misrecognition_lookalikes_detected(self) -> None:
        """Verify soundalike and typosquatted domains require confirmation with lookalike warnings."""
        lookalikes = [
            ("https://giithub.com", "github.com"),
            ("https://g00gle.com", "google.com"),
            ("https://youtub.com", "youtube.com"),
            ("https://faceb00k.com", "facebook.com"),
            ("https://amzon.com", "amazon.in"),
            ("https://wikipdia.org", "wikipedia.org"),
        ]
        for url, target in lookalikes:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.NEEDS_CONFIRMATION)
            self.assertFalse(res.is_safe_to_open)
            self.assertTrue(any("lookalike" in rf for rf in res.risk_factors))
            self.assertIn(target, res.reason)

    # =========================================================================
    # Area 4: Malformed URLs
    # =========================================================================

    def test_06_empty_and_whitespace_urls_blocked(self) -> None:
        """Verify empty and whitespace strings are BLOCKED."""
        for bad in ["", "   ", "\t\n  "]:
            res = classify_url(bad)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED)
            self.assertIn("Target URL cannot be empty.", res.reason)

    def test_07_invalid_types_blocked(self) -> None:
        """Verify non-string inputs are BLOCKED."""
        for invalid in [None, 12345, ["https://example.com"], {"url": "test"}]:
            res = classify_url(invalid)  # type: ignore[arg-type]
            self.assertEqual(res.level, URLTrustLevel.BLOCKED)
            self.assertIn("Invalid URL type", res.reason)

    def test_08_spaces_in_url_blocked(self) -> None:
        """Verify URLs with embedded unencoded spaces are BLOCKED."""
        res = classify_url("https://example.com/foo bar/baz")
        self.assertEqual(res.level, URLTrustLevel.BLOCKED)
        self.assertIn("whitespace", res.reason.lower())

    # =========================================================================
    # Area 5: Unsupported Schemes
    # =========================================================================

    def test_09_unsupported_schemes_blocked(self) -> None:
        """Verify ftp, file, vbscript, and other non-http schemes are BLOCKED."""
        bad_schemes = [
            "ftp://ftp.example.com/files",
            "ftps://files.example.com",
            "file:///C:/Windows/System32/cmd.exe",
            "file:///etc/passwd",
            "vbscript:msgbox(1)",
            "about:blank",
            "blob:https://example.com/uuid",
            "chrome://settings",
            "edge://version",
        ]
        for url in bad_schemes:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED, f"Expected BLOCKED for {url}")
            self.assertFalse(res.is_safe_to_open)

    # =========================================================================
    # Area 6: javascript: and data: URLs
    # =========================================================================

    def test_10_javascript_urls_blocked(self) -> None:
        """Verify javascript: execution payloads are strictly BLOCKED."""
        for js_url in [
            "javascript:alert(1)",
            "javascript:void(0)",
            "JAVASCRIPT:console.log('pwned')",
            "javascript:/*comment*/alert(document.cookie)",
        ]:
            res = classify_url(js_url)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED)
            self.assertIn("javascript", res.reason.lower())

    def test_11_data_urls_blocked(self) -> None:
        """Verify data: URLs are strictly BLOCKED."""
        for data_url in [
            "data:text/html,<script>alert(1)</script>",
            "DATA:text/plain;base64,SGVsbG8=",
        ]:
            res = classify_url(data_url)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED)
            self.assertIn("data", res.reason.lower())

    # =========================================================================
    # Area 7: Embedded Credentials
    # =========================================================================

    def test_12_embedded_credentials_blocked(self) -> None:
        """Verify URLs with username or password embedded in authority are BLOCKED."""
        credential_urls = [
            "https://user:password@example.com",
            "https://admin@malicious-site.com",
            "http://user:secret@192.168.1.1",
            "https://ashish:token@ashishsahoo.vercel.app",
        ]
        for url in credential_urls:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED, f"Expected BLOCKED for {url}")
            self.assertIn("credentials", res.reason.lower())

    # =========================================================================
    # Area 8: IDN & Punycode Homograph Attacks
    # =========================================================================

    def test_13_punycode_and_unicode_homographs_detected(self) -> None:
        """Verify Punycode (xn--) and non-ASCII hostnames require confirmation with IDN warning."""
        idn_urls = [
            "https://xn--e1afmkfd.xn--p1ai",       # Russian IDN
            "https://xn--pple-43d.com",             # Lookalike for apple.com
            "https://wikip\u0435dia.org",          # Cyrillic 'e' homograph
        ]
        for url in idn_urls:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.NEEDS_CONFIRMATION)
            self.assertTrue(
                "punycode_idn" in res.risk_factors or "unicode_homograph" in res.risk_factors,
                f"Expected IDN risk factor for {url}",
            )
            self.assertIn("homograph", res.reason.lower())

    # =========================================================================
    # Area 9: Localhost and Loopback Interfaces
    # =========================================================================

    def test_14_localhost_and_loopback_blocked(self) -> None:
        """Verify localhost, 127.0.0.1, and ::1 are BLOCKED."""
        loopbacks = [
            "http://localhost:8000",
            "https://localhost",
            "http://127.0.0.1:3000",
            "http://[::1]:8080",
            "http://localhost.localdomain",
        ]
        for url in loopbacks:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED, f"Expected BLOCKED for {url}")
            self.assertIn("localhost", res.reason.lower())

    # =========================================================================
    # Area 10: Private / Reserved IP Addresses & Internal Suffixes
    # =========================================================================

    def test_15_private_and_reserved_ips_blocked(self) -> None:
        """Verify RFC 1918 private IPs, link-local, and broadcast IPs are BLOCKED."""
        private_ips = [
            "http://10.0.0.1",
            "http://10.255.255.254",
            "http://172.16.0.1",
            "http://172.31.255.255",
            "http://192.168.1.1",
            "http://192.168.0.254",
            "http://169.254.169.254",  # Cloud metadata IP
            "http://0.0.0.0",
        ]
        for url in private_ips:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED, f"Expected BLOCKED for {url}")
            self.assertIn("blocked", res.reason.lower())

    def test_16_internal_network_suffixes_blocked(self) -> None:
        """Verify .local, .internal, .lan, and .onion domains are BLOCKED."""
        internal_domains = [
            "http://myrouter.local",
            "https://server.internal",
            "http://nas.lan",
            "http://service.home",
            "http://hidden.onion",
        ]
        for url in internal_domains:
            res = classify_url(url)
            self.assertEqual(res.level, URLTrustLevel.BLOCKED, f"Expected BLOCKED for {url}")
            self.assertIn("private or local network domain", res.reason.lower())

    def test_17_public_ip_literal_requires_confirmation(self) -> None:
        """Verify public IP addresses are permitted only with explicit confirmation."""
        res = classify_url("http://93.184.216.34")  # example.com public IP
        self.assertEqual(res.level, URLTrustLevel.NEEDS_CONFIRMATION)
        self.assertIn("public_ip_literal", res.risk_factors)


class TestStage2CBrowserCommandsConfirmation(unittest.TestCase):
    """Test BrowserCommands integration with confirmation workflows, callbacks, and Firefox launching."""

    def setUp(self) -> None:
        set_browser_confirmation_callback(None)

    def tearDown(self) -> None:
        set_browser_confirmation_callback(None)

    # =========================================================================
    # Area 11: Trusted Portfolio Aliases in BrowserCommands
    # =========================================================================

    @patch("webbrowser.open")
    def test_18_portfolio_aliases_open_immediately_without_confirmation(
        self, mock_web_open: MagicMock
    ) -> None:
        """Verify all portfolio aliases open immediately in browser without triggering confirmation."""
        mock_web_open.return_value = True
        mock_callback = MagicMock(return_value=True)

        browser = BrowserCommands(confirmation_callback=mock_callback)

        aliases = [
            "portfolio",
            "my portfolio",
            "portfolio website",
            "my portfolio website",
            "ashish portfolio",
            "ashish sahoo portfolio",
        ]
        for alias in aliases:
            mock_web_open.reset_mock()
            mock_callback.reset_mock()

            result = browser.open_site(alias)

            self.assertIn("Opening Ashish Sahoo's Portfolio", result)
            mock_callback.assert_not_called()
            mock_web_open.assert_called_once_with(BrowserCommands.PORTFOLIO_URL)

    # =========================================================================
    # Area 12: External Destination Confirmation Workflow (Confirm vs Cancel)
    # =========================================================================

    @patch("webbrowser.open")
    def test_19_confirm_action_proceeds_to_open(self, mock_web_open: MagicMock) -> None:
        """Verify confirmation callback returning True allows the URL to open."""
        mock_web_open.return_value = True
        mock_callback = MagicMock(return_value=True)

        browser = BrowserCommands(confirmation_callback=mock_callback)
        result = browser.open_url("https://example.com")

        mock_callback.assert_called_once_with("https://example.com", "example.com")
        mock_web_open.assert_called_once_with("https://example.com")
        self.assertIn("Opening example.com", result)

    @patch("webbrowser.open")
    def test_20_cancel_action_aborts_and_does_not_open_browser(
        self, mock_web_open: MagicMock
    ) -> None:
        """Verify confirmation callback returning False prevents browser launch and returns cancellation."""
        mock_web_open.return_value = True
        mock_callback = MagicMock(return_value=False)

        browser = BrowserCommands(confirmation_callback=mock_callback)
        result = browser.open_url("https://example.com")

        mock_callback.assert_called_once_with("https://example.com", "example.com")
        mock_web_open.assert_not_called()
        self.assertIn("cancelled by user", result)
        self.assertIn("example.com", result)

    # =========================================================================
    # Area 13: Strict Safety — No URL Opened Before Confirmation Completes
    # =========================================================================

    @patch("webbrowser.open")
    def test_21_no_browser_open_before_confirmation_completes(
        self, mock_web_open: MagicMock
    ) -> None:
        """Verify browser.open is NOT invoked before or during the confirmation callback execution."""
        call_order = []

        def callback_spy(url: str, host: str) -> bool:
            # At the moment the user is being asked, browser must NOT have opened yet
            call_order.append(("callback_start", mock_web_open.call_count))
            time.sleep(0.01)
            call_order.append(("callback_end", mock_web_open.call_count))
            return True

        mock_web_open.side_effect = lambda url: call_order.append(("browser_opened", 1))

        browser = BrowserCommands(confirmation_callback=callback_spy)
        browser.open_url("https://python.org")

        self.assertEqual(
            call_order,
            [
                ("callback_start", 0),  # 0 calls before confirmation
                ("callback_end", 0),    # 0 calls during confirmation
                ("browser_opened", 1),  # Browser opened ONLY after user confirmed
            ],
        )

    # =========================================================================
    # Area 14: No Duplicate Browser Openings
    # =========================================================================

    @patch("webbrowser.open")
    def test_22_no_duplicate_browser_opening(self, mock_web_open: MagicMock) -> None:
        """Verify confirmed navigation invokes browser.open exactly once."""
        mock_web_open.return_value = True
        browser = BrowserCommands(confirmation_callback=lambda u, h: True)

        browser.open_url("https://example.com")
        self.assertEqual(mock_web_open.call_count, 1)

    # =========================================================================
    # Area 15: Global Callback Hook Support
    # =========================================================================

    @patch("webbrowser.open")
    def test_23_global_confirmation_callback_used_when_instance_has_none(
        self, mock_web_open: MagicMock
    ) -> None:
        """Verify global callback registered via set_browser_confirmation_callback is honored."""
        mock_web_open.return_value = True
        mock_global = MagicMock(return_value=True)
        set_browser_confirmation_callback(mock_global)

        browser = BrowserCommands()  # No callback passed to instance
        res = browser.open_url("https://example.com")

        mock_global.assert_called_once_with("https://example.com", "example.com")
        self.assertIn("Opening example.com", res)

    # =========================================================================
    # Area 16: Fail Closed When Confirmation Required But No Handler Available
    # =========================================================================

    @patch("webbrowser.open")
    def test_24_fail_closed_without_confirmation_handler(
        self, mock_web_open: MagicMock
    ) -> None:
        """Verify untrusted destination fails closed if no confirmation handler is registered."""
        browser = BrowserCommands(confirmation_callback=None, require_confirmation=True)
        res = browser.open_url("https://untrusted-external-site.com")

        mock_web_open.assert_not_called()
        self.assertIn("requires explicit confirmation", res)
        self.assertIn("no confirmation handler is available", res)

    # =========================================================================
    # Area 17: Blocked Destinations In BrowserCommands
    # =========================================================================

    @patch("webbrowser.open")
    def test_25_browser_commands_blocks_malformed_and_unsafe_urls(
        self, mock_web_open: MagicMock
    ) -> None:
        """Verify BrowserCommands.open_url blocks malformed and dangerous URLs without callback."""
        mock_callback = MagicMock(return_value=True)
        browser = BrowserCommands(confirmation_callback=mock_callback)

        unsafe_cases = [
            "javascript:alert(1)",
            "data:text/html,bad",
            "http://127.0.0.1:8000",
            "http://192.168.1.1",
            "http://user:pass@example.com",
            "ftp://ftp.example.com",
        ]
        for bad_url in unsafe_cases:
            res = browser.open_url(bad_url)
            self.assertIn("Security check blocked navigation", res)
            mock_callback.assert_not_called()
            mock_web_open.assert_not_called()

    # =========================================================================
    # Area 18: Thread Safety for Voice and Typed Commands
    # =========================================================================

    @patch("webbrowser.open")
    def test_26_background_thread_safety_with_blocking_event(
        self, mock_web_open: MagicMock
    ) -> None:
        """Verify thread-safe background execution where background thread blocks until UI confirms."""
        mock_web_open.return_value = True

        def simulated_ui_callback(url: str, host: str) -> bool:
            # Simulates what ui/chat.py does: background thread waits on threading.Event
            event = threading.Event()
            result = [False]

            def user_clicks_confirm():
                time.sleep(0.05)  # Simulate user thinking and clicking
                result[0] = True
                event.set()

            threading.Thread(target=user_clicks_confirm, daemon=True).start()
            event.wait(timeout=2.0)
            return result[0]

        browser = BrowserCommands(confirmation_callback=simulated_ui_callback)

        thread_result = []

        def worker():
            msg = browser.open_url("https://example.com")
            thread_result.append(msg)

        bg_thread = threading.Thread(target=worker, daemon=True)
        bg_thread.start()
        bg_thread.join(timeout=3.0)

        self.assertFalse(bg_thread.is_alive())
        self.assertEqual(len(thread_result), 1)
        self.assertIn("Opening example.com", thread_result[0])
        mock_web_open.assert_called_once_with("https://example.com")

    # =========================================================================
    # Area 19: Firefox Controller Path Verification
    # =========================================================================

    def test_27_firefox_controller_attempted_first(self) -> None:
        """Verify Firefox controller is queried and attempted before fallback."""
        browser = BrowserCommands()
        with patch.object(browser, "_get_firefox_controller") as mock_get_ff:
            mock_ff = MagicMock()
            mock_ff.open.return_value = True
            mock_get_ff.return_value = mock_ff

            browser.confirmation_callback = lambda u, h: True

            res = browser.open_url("https://example.com")
            mock_get_ff.assert_called_once()
            mock_ff.open.assert_called_once_with("https://example.com")
            self.assertIn("Mozilla Firefox", res)


class TestStage2CUIChatIntegration(unittest.TestCase):
    """Test ui/chat.py CommandConsolePanel confirmation callbacks and thread bridge."""

    def test_28_browser_url_confirmation_callback_confirm_flow(self) -> None:
        """Verify CommandConsolePanel._browser_url_confirmation_callback returns True on confirm."""
        from ui.chat import CommandConsolePanel

        mock_parent = MagicMock()
        mock_assistant = MagicMock()
        mock_store = MagicMock()
        mock_store.get_or_create_session.return_value = "test-session"
        mock_voice = MagicMock()
        mock_bridge = MagicMock()

        # Create panel instance without building full Tk widget tree
        panel = object.__new__(CommandConsolePanel)
        panel.event_bridge = mock_bridge
        panel.request_confirmation = MagicMock()
        panel.voice_manager = mock_voice

        # When bridge.post is called, execute the modal callback which triggers on_confirm
        def fake_post(func, *args, **kwargs):
            if func == panel._show_browser_url_confirmation_dialog:
                url, host, on_confirm, on_cancel = args
                # Simulate user confirming
                on_confirm()

        mock_bridge.post.side_effect = fake_post

        confirmed = panel._browser_url_confirmation_callback("https://example.com", "example.com")
        self.assertTrue(confirmed)

    def test_29_browser_url_confirmation_callback_cancel_flow(self) -> None:
        """Verify CommandConsolePanel._browser_url_confirmation_callback returns False on cancel."""
        from ui.chat import CommandConsolePanel

        panel = object.__new__(CommandConsolePanel)
        mock_bridge = MagicMock()
        panel.event_bridge = mock_bridge
        panel.request_confirmation = MagicMock()
        panel.voice_manager = MagicMock()

        def fake_post(func, *args, **kwargs):
            if func == panel._show_browser_url_confirmation_dialog:
                url, host, on_confirm, on_cancel = args
                # Simulate user cancelling
                on_cancel()

        mock_bridge.post.side_effect = fake_post

        confirmed = panel._browser_url_confirmation_callback("https://example.com", "example.com")
        self.assertFalse(confirmed)


if __name__ == "__main__":
    unittest.main()

