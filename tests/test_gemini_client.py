import unittest
from ai.gemini_client import GeminiClient, generate_ai_response, ask_ai, OFFLINE_RESPONSE


class GeminiClientDisabledTests(unittest.TestCase):
    def test_ai_answering_disabled(self) -> None:
        client = GeminiClient()
        res = client.ask("What is Python?")
        self.assertEqual(res, OFFLINE_RESPONSE)

    def test_wrappers_disabled(self) -> None:
        self.assertEqual(generate_ai_response("What is AI?"), OFFLINE_RESPONSE)
        self.assertEqual(ask_ai("What is AI?"), OFFLINE_RESPONSE)


if __name__ == "__main__":
    unittest.main()
