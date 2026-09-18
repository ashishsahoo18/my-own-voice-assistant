import os
import unittest
from unittest.mock import MagicMock, patch
from ai.ai_service import AIService


class LocalAIServiceHealthCheckTests(unittest.TestCase):
    def test_ai_service_offline_notice(self) -> None:
        """When Ollama is offline or connection fails, returns exact offline notice."""
        with patch("requests.get", side_effect=Exception("Connection refused")):
            ai_service = AIService()
            res = ai_service.ask("What is recursion?")
            self.assertEqual(res, "Local AI is offline. Please start Ollama.")

    @patch("requests.get")
    def test_ai_service_no_models_installed(self, mock_get: MagicMock) -> None:
        """When Ollama is online but 0 models installed, returns clear model setup instruction."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}
        mock_get.return_value = mock_resp

        ai_service = AIService()
        res = ai_service.ask("What is recursion?")
        self.assertIn("No local AI model is installed", res)

    @patch("requests.post")
    @patch("requests.get")
    def test_ai_service_online_response(self, mock_get: MagicMock, mock_post: MagicMock) -> None:
        """When Ollama is online with model installed, returns generated response."""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": "Recursion is a programming concept where a function calls itself."
            }
        }
        mock_post.return_value = mock_post_resp

        ai_service = AIService()
        res = ai_service.ask("What is recursion?")
        self.assertIn("Recursion is a programming concept", res)

    @patch("requests.post")
    @patch("requests.get")
    def test_model_auto_detection(self, mock_get: MagicMock, mock_post: MagicMock) -> None:
        """When configured model is absent, auto-selects first available model."""
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"models": [{"name": "gemma:2b"}]}
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"message": {"content": "Auto selected model answer."}}
        mock_post.return_value = mock_post_resp

        with patch.dict(os.environ, {"OLLAMA_MODEL": "non_existent_model"}, clear=False):
            ai_service = AIService()
            res = ai_service.ask("What is polymorphism in C++?")
            self.assertEqual(res, "Auto selected model answer.")

    def test_greeting_response(self) -> None:
        """Greeting inputs return friendly local assistant greeting."""
        ai_service = AIService()
        res = ai_service.ask("Hello Ashish AI")
        self.assertIn("Hello! I am ASHISH AI", res)


if __name__ == "__main__":
    unittest.main()
