import unittest

from ai.gemini_client import GeminiClient


class GeminiClientQuotaHandlingTests(unittest.TestCase):
    def test_detects_quota_exhaustion_errors(self) -> None:
        client = GeminiClient()

        self.assertTrue(
            client._is_quota_error(Exception("RESOURCE_EXHAUSTED: generate_content_free_tier_input_token_count"))
        )
        self.assertTrue(client._is_quota_error(Exception("429 Too Many Requests")))
        self.assertTrue(client._is_quota_error(Exception("Quota exceeded for metric")))
        self.assertFalse(client._is_quota_error(Exception("Something else failed")))


if __name__ == "__main__":
    unittest.main()
