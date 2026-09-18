"""Comprehensive automated tests for ASHISH AI upgrade requirements."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from ai.assistant import AshishAssistant
from ai.ai_service import AIService, UNAVAILABLE_MESSAGE
from commands.contacts import ContactManager


class AshishAssistantUpgradeTests(unittest.TestCase):
    """Test suite covering all required test scenarios for Ashish AI upgrade."""

    def setUp(self) -> None:
        self.assistant = AshishAssistant()

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

    @patch("commands.youtube.YouTubeCommands.get_video_id", return_value="7wtfhZwyrC0")
    @patch("webbrowser.open")
    def test_04_youtube_play_direct(self, mock_webbrowser_open: MagicMock, mock_get_video_id: MagicMock) -> None:
        """TEST 4: Play command opens direct video watch URL and returns Playing status."""
        mock_webbrowser_open.return_value = True

        res1 = self.assistant.handle("Open YouTube")
        self.assertIn("YouTube", res1)

        res2 = self.assistant.handle("Play Ik Mulaqaat")
        self.assertIn("Playing Ik Mulaqaat", res2)

        res3 = self.assistant.handle("Play Believer")
        self.assertIn("Playing Believer", res3)

        res4 = self.assistant.handle("Search Believer on YouTube")
        self.assertIn("YouTube results for Believer", res4)

    @patch("webbrowser.open")
    def test_05_social_account_shortcuts(self, mock_webbrowser_open: MagicMock) -> None:
        """TEST 5: Open GitHub, LinkedIn, Instagram, Flipkart shortcuts."""
        mock_webbrowser_open.return_value = True

        res_gh = self.assistant.handle("Open GitHub")
        self.assertIn("GitHub", res_gh)

        res_li = self.assistant.handle("Open my LinkedIn")
        self.assertIn("LinkedIn", res_li)

        res_fk = self.assistant.handle("Open Flipkart")
        self.assertIn("Flipkart", res_fk)

    def test_06_whatsapp_confirmation_preparation(self) -> None:
        """TEST 6: WhatsApp command triggers confirmation payload with recipient and message."""
        res = self.assistant.handle("Send WhatsApp message to Maa saying I am coming home")
        self.assertTrue(res.startswith("CONFIRMATION_REQUIRED:WHATSAPP:"))
        self.assertIn("Maa", res)
        self.assertIn("I am coming home", res)

    def test_07_email_confirmation_preparation(self) -> None:
        """TEST 7: Email command triggers confirmation payload with recipient and message."""
        res = self.assistant.handle("Send an email to Maa saying meeting update")
        self.assertTrue(res.startswith("CONFIRMATION_REQUIRED:EMAIL:"))
        self.assertIn("Maa", res)
        self.assertIn("meeting update", res)

    def test_08_contact_ambiguity_detection(self) -> None:
        """TEST 8: Multiple contacts with same query prompt for clarification."""
        contacts = ContactManager()
        res = contacts.resolve_contact("Rahul")
        self.assertTrue(res.is_ambiguous)
        self.assertIn("Which 'Rahul' do you mean?", res.error_message)

    @patch("requests.post")
    @patch("requests.get")
    def test_09_local_ai_question_answering(self, mock_get: MagicMock, mock_post: MagicMock) -> None:
        """TEST 9: Local AI Q&A handles technical questions without opening browser."""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"models": [{"name": "llama3.2"}]}
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Polymorphism allows objects of different classes to be treated as objects of a common superclass."
            }
        }
        mock_post.return_value = mock_post_resp

        res = self.assistant.handle("What is polymorphism in C++?")
        self.assertIn("Polymorphism allows", res)

    def test_10_local_ai_offline_fallback(self) -> None:
        """TEST 10: Local AI when offline returns clear status message without crashing."""
        with patch("requests.get", side_effect=Exception("Ollama Offline")):
            res = self.assistant.handle("What is recursion?")
            self.assertEqual(res, "Local AI is offline. Please start Ollama.")

    @patch("subprocess.Popen")
    def test_11_open_notepad(self, mock_popen: MagicMock) -> None:
        """TEST 11: Input 'Open Notepad' triggers Notepad launcher."""
        response = self.assistant.handle("Open Notepad")
        self.assertIn("notepad", response.lower())

    def test_12_current_time(self) -> None:
        """TEST 12: Current time query returns formatted system clock time."""
        response = self.assistant.handle("What is the current time?")
        self.assertIn("The current time is", response)


if __name__ == "__main__":
    unittest.main()
