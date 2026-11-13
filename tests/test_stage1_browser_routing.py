"""Comprehensive test suite for Phase 2A.1.3 Stage 1 & Stage 1.1: Browser routing and tool argument reliability."""

import unittest
from unittest.mock import MagicMock, patch

from browser.models import BrowserAnswerResult
from execution.engine import ExecutionEngine
from execution.request import TaskRequest
from router.router import IntentRouter
from skills.builtin.browser_skill import BrowserSkill
from skills.registry import SkillRegistry


class TestBrowserRoutingAndArgumentReliability(unittest.TestCase):
    """Test deterministic ask-page routing, argument compatibility, prompt enhancements, and pipeline integration."""

    def setUp(self) -> None:
        self.mock_service = MagicMock()
        self.mock_service.ask_page.return_value = BrowserAnswerResult(
            status="VERIFIED",
            question="dummy question",
            answer="Guido van Rossum",
            source_url="https://example.com",
            has_evidence=True,
            citations=["[Example](https://example.com)"],
            message="Answer generated from [https://example.com].",
        )
        self.skill = BrowserSkill(service=self.mock_service)
        self.router = IntentRouter()

    # =========================================================================
    # Area 1: Deterministic Routing
    # =========================================================================

    def test_01_ask_page_about_python(self) -> None:
        """Verify 'ask page about Python' selects browser.ask_page with extracted question."""
        res = self.router.route("ask page about Python")
        self.assertTrue(res.matched)
        self.assertEqual(res.tool_name, "browser.ask_page")
        self.assertEqual(res.arguments.get("question"), "about Python")

    def test_02_ask_the_page_about_python(self) -> None:
        """Verify 'Ask the page about Python' matches deterministically."""
        res = self.router.route("Ask the page about Python")
        self.assertTrue(res.matched)
        self.assertEqual(res.tool_name, "browser.ask_page")
        self.assertEqual(res.arguments.get("question"), "about Python")

    def test_03_ask_the_current_page_about_python(self) -> None:
        """Verify 'Ask the current page about Python' matches deterministically."""
        res = self.router.route("Ask the current page about Python")
        self.assertTrue(res.matched)
        self.assertEqual(res.tool_name, "browser.ask_page")
        self.assertEqual(res.arguments.get("question"), "about Python")

    def test_04_ask_this_page_who_created_python(self) -> None:
        """Verify 'ask this page who created Python' extracts the complete question."""
        res = self.router.route("ask this page who created Python")
        self.assertTrue(res.matched)
        self.assertEqual(res.tool_name, "browser.ask_page")
        self.assertEqual(res.arguments.get("question"), "who created Python")

    def test_05_ask_webpage_about_django(self) -> None:
        """Verify 'ask webpage about Django' selects browser.ask_page."""
        res = self.router.route("ask webpage about Django")
        self.assertTrue(res.matched)
        self.assertEqual(res.tool_name, "browser.ask_page")
        self.assertEqual(res.arguments.get("question"), "about Django")

    def test_06_ask_this_webpage_to_explain_django(self) -> None:
        """Verify 'Ask this webpage to explain Django' strips 'to' and extracts question."""
        res = self.router.route("Ask this webpage to explain Django")
        self.assertTrue(res.matched)
        self.assertEqual(res.tool_name, "browser.ask_page")
        self.assertEqual(res.arguments.get("question"), "explain Django")

    def test_07_ask_the_webpage_to_explain_its_content(self) -> None:
        """Verify 'Ask the webpage to explain its content' matches deterministically."""
        res = self.router.route("Ask the webpage to explain its content")
        self.assertTrue(res.matched)
        self.assertEqual(res.tool_name, "browser.ask_page")
        self.assertEqual(res.arguments.get("question"), "explain its content")

    def test_08_case_insensitive_matching(self) -> None:
        """Verify ask-page command matches across different casing styles."""
        for phrase in [
            "ASK PAGE ABOUT PYTHON",
            "Ask This Page Who Created Python",
            "aSk WeBpAgE aBoUt DjAnGo",
            "ASK THE CURRENT PAGE TO EXPLAIN ITS CONTENT",
        ]:
            res = self.router.route(phrase)
            self.assertTrue(res.matched, f"Failed case-insensitive match for: {phrase}")
            self.assertEqual(res.tool_name, "browser.ask_page")
            self.assertIn("question", res.arguments)

    def test_09_empty_or_incomplete_ask_page_commands(self) -> None:
        """Verify empty/incomplete phrases do not route to browser.ask_page without question."""
        for phrase in ["ask page", "ask webpage", "ask the page", "ask the current page"]:
            res = self.router.route(phrase)
            self.assertNotEqual(
                res.tool_name,
                "browser.ask_page",
                f"Incomplete phrase '{phrase}' should not match browser.ask_page without a question",
            )

    def test_10_unrelated_commands_do_not_match_ask_page(self) -> None:
        """Verify unrelated commands are not accidentally captured by ask-page pattern."""
        unrelated = [
            ("ask about python", "ai.ask"),
            ("what is python", "ai.ask"),
            ("open youtube", "browser.open_site"),
            ("open page https://example.com", "browser.open_page"),
            ("summarize page https://example.com", "browser.summarize_page"),
            ("close browser", "browser.close_session"),
        ]
        for cmd, expected_tool in unrelated:
            res = self.router.route(cmd)
            self.assertNotEqual(
                res.tool_name,
                "browser.ask_page",
                f"Unrelated command '{cmd}' should not route to browser.ask_page",
            )
            self.assertEqual(res.tool_name, expected_tool)

    # =========================================================================
    # Area 2: Argument Validation in BrowserSkill.ask_page
    # =========================================================================

    def test_11_valid_question_argument(self) -> None:
        """Verify call with valid 'question' succeeds."""
        result = self.skill.ask_page(question="who created Python")
        self.assertEqual(result.status, "VERIFIED")
        self.mock_service.ask_page.assert_called_with(question="who created Python", url=None)

    def test_12_valid_legacy_query_argument(self) -> None:
        """Verify legacy 'query' argument is safely accepted when question is omitted."""
        result = self.skill.ask_page(query="who created Python")
        self.assertEqual(result.status, "VERIFIED")
        self.mock_service.ask_page.assert_called_with(question="who created Python", url=None)

    def test_13_identical_question_and_query_accepted(self) -> None:
        """Verify providing identical text in both question and query is accepted."""
        result = self.skill.ask_page(question="who created Python", query="who created Python")
        self.assertEqual(result.status, "VERIFIED")
        self.mock_service.ask_page.assert_called_with(question="who created Python", url=None)

    def test_14_conflicting_question_and_query_rejected(self) -> None:
        """Verify conflicting question and query arguments are explicitly rejected."""
        result = self.skill.ask_page(question="who created Python", query="what is Django")
        self.assertEqual(result.status, "FAILED")
        self.assertIn("ConflictingArguments", result.error)

    def test_15_missing_both_question_and_query(self) -> None:
        """Verify omission of both question and query returns FAILED with MissingArgument."""
        result = self.skill.ask_page()
        self.assertEqual(result.status, "FAILED")
        self.assertIn("MissingArgument", result.error)

    def test_16_empty_and_whitespace_only_questions(self) -> None:
        """Verify empty string and whitespace-only questions are rejected."""
        for empty_val in ["", "   ", "\t\n  "]:
            res_q = self.skill.ask_page(question=empty_val)
            self.assertEqual(res_q.status, "FAILED")
            self.assertIn("MissingArgument", res_q.error)

            res_query = self.skill.ask_page(query=empty_val)
            self.assertEqual(res_query.status, "FAILED")
            self.assertIn("MissingArgument", res_query.error)

    def test_17_unexpected_keyword_arguments_rejected(self) -> None:
        """Verify unexpected extra kwargs are rejected with UnexpectedArgument."""
        result = self.skill.ask_page(question="valid question", bogus_param="bad", extra_flag=True)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("UnexpectedArgument", result.error)
        self.assertIn("bogus_param", result.error)
        self.assertIn("extra_flag", result.error)

    def test_18_invalid_argument_types_rejected(self) -> None:
        """Verify non-string question arguments are rejected with InvalidType."""
        for invalid_val in [12345, ["who", "created"], {"q": "python"}, 3.14]:
            result = self.skill.ask_page(question=invalid_val)
            self.assertEqual(result.status, "FAILED")
            self.assertIn("InvalidType", result.error)

    # =========================================================================
    # Area 3: LLM Parameter Inspection
    # =========================================================================

    def test_19_llm_parameter_inspection_and_prompt_formatting(self) -> None:
        """Verify tool classification prompt reflects exact parameter names and classifications."""
        with patch.object(self.router.llm, "structured_output") as mock_llm:
            mock_llm.return_value = None
            self.router._classify_with_llm("find information on page")

            self.assertTrue(mock_llm.called)
            prompt_called = mock_llm.call_args[1].get("prompt") or mock_llm.call_args[0][0]

            # Verify browser.ask_page parameter specifications
            self.assertIn("browser.ask_page", prompt_called)
            self.assertIn("question (required)", prompt_called)
            self.assertIn("url (optional, default=None)", prompt_called)

            # Verify query alias is hidden from browser.ask_page arguments list
            ask_page_line = [line for line in prompt_called.splitlines() if "browser.ask_page" in line or "Supported arguments: [question" in line]
            self.assertTrue(any("browser.ask_page" in l for l in ask_page_line))
            self.assertIn("Supported arguments: [question (required), url (optional, default=None)]", prompt_called)

            # Verify example JSON output uses valid argument names
            self.assertIn('{"question": "who created Python"}', prompt_called)

    # =========================================================================
    # Area 4: Execution Pipeline Integration
    # =========================================================================

    def test_20_execution_pipeline_integration_with_mocks(self) -> None:
        """Verify end-to-end routing -> TaskRequest -> ExecutionEngine -> BrowserSkill execution."""
        registry = SkillRegistry()
        mock_service = MagicMock()
        mock_service.ask_page.return_value = BrowserAnswerResult(
            status="VERIFIED",
            question="who created Python",
            answer="Guido van Rossum",
            source_url="https://example.com",
            has_evidence=True,
            citations=["[Example](https://example.com)"],
            message="Answer generated from [https://example.com].",
        )
        skill = BrowserSkill(service=mock_service)

        router = IntentRouter(registry=registry)
        # Re-register with the mock service so the router's registry has our instrumented skill
        registry.register(skill)

        # 1. Route natural-language command
        route_res = router.route("ask this page who created Python")
        self.assertTrue(route_res.matched)
        self.assertEqual(route_res.tool_name, "browser.ask_page")
        self.assertEqual(route_res.arguments, {"question": "who created Python"})

        # 2. Dispatch through ExecutionEngine
        req = TaskRequest(
            tool_name=route_res.tool_name,
            arguments=route_res.arguments,
        )
        engine = ExecutionEngine(registry=registry)
        exec_res = engine.execute(req, registry=registry)

        # 3. Verify handler and service received correct arguments
        self.assertEqual(exec_res.status, "VERIFIED")
        mock_service.ask_page.assert_called_with(question="who created Python", url=None)
        self.assertIn("Guido van Rossum", exec_res.data.get("answer", ""))

    # =========================================================================
    # Area 5: Browser Regression & Complex URL Preservation
    # =========================================================================

    def test_21_browser_routes_and_complex_urls_preserved(self) -> None:
        """Verify existing browser routes handle complex URLs with queries, fragments, and percent-encoding."""
        complex_url = "https://example.com/search?q=hello%20world&lang=en#section-2"

        r_open = self.router.route(f"open page {complex_url}")
        self.assertTrue(r_open.matched)
        self.assertEqual(r_open.tool_name, "browser.open_page")
        self.assertEqual(r_open.arguments.get("url"), complex_url)

        r_sum = self.router.route(f"summarize page {complex_url}")
        self.assertTrue(r_sum.matched)
        self.assertEqual(r_sum.tool_name, "browser.summarize_page")
        self.assertEqual(r_sum.arguments.get("url"), complex_url)

        r_close = self.router.route("close browser")
        self.assertTrue(r_close.matched)
        self.assertEqual(r_close.tool_name, "browser.close_session")

        r_site = self.router.route("open youtube")
        self.assertTrue(r_site.matched)
        self.assertEqual(r_site.tool_name, "browser.open_site")
        self.assertEqual(r_site.arguments.get("site_name"), "youtube")


if __name__ == "__main__":
    unittest.main()
