import unittest

from ai.gemini_client import GeminiClient


class GeminiClientQuotaHandlingTests(unittest.TestCase):
    def test_trim_history_keeps_recent_messages(self) -> None:
        client = GeminiClient()
        history = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        trimmed = client._trim_history(history)
        self.assertEqual(len(trimmed), 10)
        self.assertEqual(trimmed[0]["content"], "msg5")
        self.assertEqual(trimmed[-1]["content"], "msg14")


if __name__ == "__main__":
    unittest.main()
