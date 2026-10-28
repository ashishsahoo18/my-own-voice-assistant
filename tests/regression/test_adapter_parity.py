"""Parity tests between legacy command dispatch and OLIVER 2.0 SkillRouter."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from ai.assistant import AshishAssistant
from core.config import OliverConfig
from router.router import IntentRouter


class AdapterParityTests(unittest.TestCase):
    """Verify legacy router and OLIVER skill router parity."""

    def setUp(self) -> None:
        self.legacy_assistant = AshishAssistant()
        self.legacy_assistant.config = OliverConfig(router_mode="legacy")

        self.oliver_assistant = AshishAssistant()
        self.oliver_assistant.config = OliverConfig(router_mode="oliver")
        self.oliver_assistant.oliver_router = IntentRouter()

    @patch("webbrowser.open")
    def test_open_google_parity(self, mock_open: MagicMock) -> None:
        mock_open.return_value = True
        res_legacy = self.legacy_assistant.handle("Open Google")
        res_oliver = self.oliver_assistant.handle("Open Google")

        self.assertIn("Google", res_legacy)
        self.assertIn("Google", res_oliver)

    @patch("webbrowser.open")
    def test_open_youtube_parity(self, mock_open: MagicMock) -> None:
        mock_open.return_value = True
        res_legacy = self.legacy_assistant.handle("Open YouTube")
        res_oliver = self.oliver_assistant.handle("Open YouTube")

        self.assertIn("YouTube", res_legacy)
        self.assertIn("YouTube", res_oliver)

    @patch("webbrowser.open")
    def test_search_youtube_parity(self, mock_open: MagicMock) -> None:
        mock_open.return_value = True
        query = "Search YouTube for Python tutorials"
        res_legacy = self.legacy_assistant.handle(query)
        res_oliver = self.oliver_assistant.handle(query)

        self.assertIn("YouTube", res_legacy)
        self.assertIn("YouTube", res_oliver)

    @patch("subprocess.Popen")
    def test_open_notepad_parity(self, mock_popen: MagicMock) -> None:
        res_legacy = self.legacy_assistant.handle("Open Notepad")
        res_oliver = self.oliver_assistant.handle("Open Notepad")

        self.assertIn("notepad", res_legacy.lower())
        self.assertIn("notepad", res_oliver.lower())

    def test_whatsapp_confirmation_parity(self) -> None:
        cmd = "Send WhatsApp message to Maa saying I am on the way"
        res_legacy = self.legacy_assistant.handle(cmd)
        res_oliver = self.oliver_assistant.handle(cmd)

        self.assertTrue(res_legacy.startswith("CONFIRMATION_REQUIRED:"))
        self.assertTrue(res_oliver.startswith("CONFIRMATION_REQUIRED:"))
        self.assertIn("Maa", res_legacy)
        self.assertIn("Maa", res_oliver)

    def test_safe_math_calculation(self) -> None:
        """Verify AST-based calculator in productivity skill works without eval."""
        router = IntentRouter()
        route = router.route("calculate 25 + 75 * 2")
        self.assertTrue(route.matched)
        self.assertEqual(route.tool_name, "productivity.calculate")

        result = router.execute_route(route)
        self.assertEqual(result, "Result: 175")


if __name__ == "__main__":
    unittest.main()
