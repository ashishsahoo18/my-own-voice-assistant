import os
import unittest
from unittest.mock import patch

from ai.gemini_client import GeminiClient


class DummyGeminiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GeminiClientQuotaHandlingTests(unittest.TestCase):
    def test_trim_history_keeps_recent_messages(self) -> None:
        client = GeminiClient()
        history = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        trimmed = client._trim_history(history)
        self.assertEqual(len(trimmed), 8)
        self.assertEqual(trimmed[0]["content"], "msg7")
        self.assertEqual(trimmed[-1]["content"], "msg14")

    def test_detects_quota_errors_from_message_and_status(self) -> None:
        client = GeminiClient()
        self.assertTrue(client._is_quota_error(DummyGeminiError("RESOURCE_EXHAUSTED: quota exceeded", 429)))
        self.assertTrue(client._is_quota_error(DummyGeminiError("Free tier quota limit reached")))
        self.assertFalse(client._is_quota_error(DummyGeminiError("Something else happened")))

    def test_accepts_custom_gemini_model_names(self) -> None:
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-2.5-pro"}, clear=False):
            client = GeminiClient()
            self.assertEqual(client._resolve_model_name(), "gemini-2.5-pro")


if __name__ == "__main__":
    unittest.main()
