"""Web research and factual synthesis skill for OLIVER 2.0."""

from __future__ import annotations

import logging
from typing import Optional

from research.models import ResearchResult, ResearchSource
from research.providers import ResearchClient
from research.sanitizer import ContentSanitizer
from research.security import SafeHTTPClient, SecurityError, SSRFValidationError
from research.summarizer import ResearchSummarizer
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec

logger = logging.getLogger("oliver.skills.research")


class ResearchSkill(BaseSkill):
    """Grounded web research skill providing verified facts, source citations, and offline transparency."""

    def __init__(
        self,
        client: Optional[ResearchClient] = None,
        summarizer: Optional[ResearchSummarizer] = None,
        http_client: Optional[SafeHTTPClient] = None,
        sanitizer: Optional[ContentSanitizer] = None,
    ) -> None:
        super().__init__()
        self.client = client or ResearchClient()
        self.summarizer = summarizer or ResearchSummarizer()
        self.http_client = http_client or SafeHTTPClient()
        self.sanitizer = sanitizer or ContentSanitizer()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="research",
            version="1.0.0",
            description="Search approved web sources, synthesize verified facts with citations, and disclose offline status.",
            triggers=["research", "search web for", "find information about", "who was", "what is"],
            dependencies=["requests", "bs4"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="research.search",
                description="Search web sources for a query, synthesize findings with source URLs, and disclose uncertainty.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.search,
            ),
            ToolSpec(
                name="research.fetch_page",
                description="Safely fetch and read a web page with SSRF protection, size bounds, and prompt injection defense.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.fetch_page,
            ),
            ToolSpec(
                name="research.explain_topic",
                description="Synthesize an encyclopedic overview of a topic using verified sources.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.explain_topic,
            ),
        ]

    def search(self, query: str, max_results: int = 3) -> ToolResult:
        """Execute grounded web research with citations and offline fallback."""
        clean_query = (query or "").strip()
        if not clean_query:
            return ToolResult(status="FAILED", message="Research query cannot be empty.")

        try:
            sources, is_offline, disclosure = self.client.query(clean_query, max_results=max_results)
            result = self.summarizer.summarize(clean_query, sources, is_offline=is_offline, disclosure=disclosure)

            formatted_markdown = result.format_markdown()
            return ToolResult(
                status="SUCCESS",
                message=formatted_markdown,
                data={
                    "query": clean_query,
                    "is_offline": result.is_offline,
                    "sources_count": len(result.sources),
                    "sources": [s.to_dict() for s in result.sources],
                    "findings_count": len(result.findings),
                },
            )
        except Exception as exc:
            logger.error("Research failed for '%s': %s", clean_query, exc)
            return ToolResult(status="FAILED", message=f"Research operation failed: {exc}")

    def fetch_page(self, url: str) -> ToolResult:
        """Safely fetch and extract text from a single web page."""
        clean_url = (url or "").strip()
        if not clean_url:
            return ToolResult(status="FAILED", message="URL cannot be empty.")

        try:
            body_text, final_url, headers = self.http_client.get(clean_url)
            clean_text = self.sanitizer.extract_text_from_html(body_text)
            safe_text, injections = self.sanitizer.neutralize_prompt_injections(clean_text)

            summary = safe_text[:1200]
            if len(safe_text) > 1200:
                summary += "\n\n...[content truncated for safety]"

            warning_note = f"\n\n⚠ Flagged {len(injections)} suspicious prompt instructions." if injections else ""
            msg = f"### Fetched Page: [{clean_url}]({final_url})\n\n{summary}{warning_note}"

            return ToolResult(
                status="SUCCESS",
                message=msg,
                data={"url": clean_url, "final_url": final_url, "injections_detected": len(injections)},
            )
        except SSRFValidationError as exc:
            return ToolResult(status="DENIED", message=f"Security Policy: Request blocked by SSRF filter ({exc})")
        except SecurityError as exc:
            return ToolResult(status="FAILED", message=f"Security Policy: {exc}")
        except Exception as exc:
            return ToolResult(status="FAILED", message=f"Failed to fetch page: {exc}")

    def explain_topic(self, topic: str) -> ToolResult:
        """Alias for research.search focused on encyclopedic explanation."""
        return self.search(f"Overview and history of {topic}")
