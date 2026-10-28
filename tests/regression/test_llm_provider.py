"""Unit tests for OllamaProvider and structured output helper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from pydantic import BaseModel

from llm.ollama_provider import OllamaProvider


class SampleSchema(BaseModel):
    name: str
    action: str
    score: int


class OllamaProviderTests(unittest.TestCase):
    """Test OllamaProvider integration, fallbacks, and structured outputs."""

    def setUp(self) -> None:
        self.provider = OllamaProvider()

    @patch("requests.get")
    def test_health_check_online(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
        mock_get.return_value = mock_resp

        is_healthy, url, model, models, err = self.provider.check_health()
        self.assertTrue(is_healthy)
        self.assertIn("llama3.2", model)
        self.assertEqual(err, "")

    @patch("requests.get")
    def test_health_check_offline(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = Exception("Connection refused")
        is_healthy, url, model, models, err = self.provider.check_health()
        self.assertFalse(is_healthy)
        self.assertIn("Local AI is offline", err)

    @patch("requests.post")
    @patch("requests.get")
    def test_ask_online(self, mock_get: MagicMock, mock_post: MagicMock) -> None:
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "message": {"role": "assistant", "content": "Recursion calls itself."}
        }
        mock_post.return_value = mock_post_resp

        ans = self.provider.ask("What is recursion?")
        self.assertEqual(ans, "Recursion calls itself.")

    @patch("requests.post")
    @patch("requests.get")
    def test_structured_output_success(self, mock_get: MagicMock, mock_post: MagicMock) -> None:
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "message": {
                "role": "assistant",
                "content": '{"name": "test_app", "action": "open", "score": 100}'
            }
        }
        mock_post.return_value = mock_post_resp

        result = self.provider.structured_output(
            prompt="Extract app action",
            schema=SampleSchema,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.name, "test_app")
        self.assertEqual(result.action, "open")
        self.assertEqual(result.score, 100)


if __name__ == "__main__":
    unittest.main()
