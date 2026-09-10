"""Comprehensive automated tests for AYRA AI upgrade requirements."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from ai.assistant import AyraAssistant
from ai.gemini_client import GeminiClient


class AyraAssistantUpgradeTests(unittest.TestCase):
    """Test suite covering all 10 required test scenarios for Ayra AI upgrade."""

    def setUp(self) -> None:
        self.assistant = AyraAssistant()

    @patch("webbrowser.open")
    def test_01_open_google(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 1: Input 'Open Google' triggers Google opening function."""
        mock_webbrowser_open.return_value = True
        response = self.assistant.handle("Open Google")
        self.assertIn("Google", response)
        mock_webbrowser_open.assert_called_with("https://www.google.com")

    @patch("webbrowser.open")
    def test_02_open_youtube(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 2: Input 'Open YouTube' triggers YouTube opening function."""
        mock_webbrowser_open.return_value = True
        response = self.assistant.handle("Open YouTube")
        self.assertIn("YouTube", response)
        mock_webbrowser_open.assert_called_with("https://www.youtube.com")

    @patch("webbrowser.open")
    def test_03_search_youtube_for_python_tutorials(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 3: Input 'Search YouTube for Python tutorials' generates correct search URL."""
        mock_webbrowser_open.return_value = True
        response = self.assistant.handle("Search YouTube for Python tutorials")
        self.assertIn("YouTube results for Python tutorials", response)
        mock_webbrowser_open.assert_called_with(
            "https://www.youtube.com/results?search_query=Python+tutorials"
        )

    @patch("webbrowser.open")
    def test_04_youtube_context_remembered(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 4: Open YouTube, then Play Believer remembers YouTube context."""
        mock_webbrowser_open.return_value = True

        res1 = self.assistant.handle("Open YouTube")
        self.assertIn("YouTube", res1)

        res2 = self.assistant.handle("Play Believer")
        self.assertIn("YouTube results for Believer", res2)
        mock_webbrowser_open.assert_called_with(
            "https://www.youtube.com/results?search_query=Believer"
        )

    @patch("webbrowser.open")
    def test_05_conversational_question_machine_learning(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 5: Input 'What is machine learning?' triggers Google search in browser."""
        mock_webbrowser_open.return_value = True
        response = self.assistant.handle("What is machine learning?")
        self.assertIn("Searching Google for What is machine learning?", response)
        mock_webbrowser_open.assert_called_with(
            "https://www.google.com/search?q=What+is+machine+learning%3F"
        )

    @patch("webbrowser.open")
    def test_06_conversational_question_explain_recursion(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 6: 'Explain recursion' triggers Google search in browser."""
        mock_webbrowser_open.return_value = True
        response = self.assistant.handle("Explain recursion.")
        self.assertIn("Searching Google for Explain recursion.", response)
        mock_webbrowser_open.assert_called_with(
            "https://www.google.com/search?q=Explain+recursion."
        )

    def test_07_run_without_gemini_api_key(self) -> None:
        """TEST 7: Ayra starts successfully without GEMINI_API_KEY."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            client = GeminiClient()
            self.assertEqual(client.api_key, "")
            self.assertIsNone(client.client)
            # Basic functionality works offline
            res = client.ask("What is Python?")
            self.assertIn("disabled", res.lower())

    def test_08_gemini_unavailable(self) -> None:
        """TEST 8: Gemini unavailable does not crash and local functionality continues."""
        client = GeminiClient()
        client.quota_exhausted = True
        res = client.ask("What is machine learning?")
        self.assertIn("disabled", res.lower())

        # Local command routing works cleanly
        with patch("webbrowser.open", return_value=True):
            res_cmd = self.assistant.handle("Open Google")
            self.assertIn("Google", res_cmd)

    @patch("subprocess.Popen")
    def test_09_open_notepad(self, mock_popen: MagicMock) -> None:
        """TEST 9: Input 'Open Notepad' triggers Notepad launcher."""
        response = self.assistant.handle("Open Notepad")
        self.assertIn("notepad", response.lower())

    @patch("webbrowser.open")
    def test_10_open_whatsapp(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 10: Input 'Open WhatsApp' triggers WhatsApp browser/launcher."""
        mock_webbrowser_open.return_value = True
        response = self.assistant.handle("Open WhatsApp")
        self.assertIn("WhatsApp", response)

    def test_11_current_time(self) -> None:
        """TEST 11: Current time query returns formatted system clock time."""
        response = self.assistant.handle("What is the current time?")
        self.assertIn("The current time is", response)

    @patch("webbrowser.open")
    def test_12_computer_science_question(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 12: Computer science query triggers Google search in browser."""
        mock_webbrowser_open.return_value = True
        response = self.assistant.handle("what is basic knowledge of computer science")
        self.assertIn("Searching Google for what is basic knowledge of computer science", response)


if __name__ == "__main__":
    unittest.main()
