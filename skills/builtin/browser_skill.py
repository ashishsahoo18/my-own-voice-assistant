"""Web browser navigation, search, and secure automation skill for OLIVER 2.0."""

from __future__ import annotations

from typing import Optional

from browser.service import BrowserService
from commands.browser import BrowserCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class BrowserSkill(BaseSkill):
    """Adapter wrapping web browser shortcuts, searching, and isolated read-only automation."""

    def __init__(self, service: Optional[BrowserService] = None) -> None:
        super().__init__()
        self.browser = BrowserCommands()
        self.service = service or BrowserService()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="browser",
            version="2.0.0",
            description="Open approved websites, extract readable content, summarize pages, and answer grounded questions.",
            triggers=[
                "open google", "open youtube", "open github", "open linkedin",
                "open flipkart", "search google for", "search github for",
                "open page", "browse to", "summarize page", "ask page", "close browser",
            ],
            dependencies=["selenium", "beautifulsoup4", "requests"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            # Legacy command shortcuts (preserved for backwards compatibility)
            ToolSpec(
                name="browser.open_site",
                description="Open a recognized website shortcut in the default browser.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.open_site,
            ),
            ToolSpec(
                name="browser.search_google",
                description="Search Google for a query.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.search_google,
            ),
            ToolSpec(
                name="browser.search_github",
                description="Search GitHub for repositories or code.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.search_github,
            ),
            ToolSpec(
                name="browser.search_stackoverflow",
                description="Search Stack Overflow for technical questions.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.search_stackoverflow,
            ),

            # Verified Read-Only Automation Tools (Capability 4)
            ToolSpec(
                name="browser.open_page",
                description="Navigate to an approved URL in an isolated profile and extract readable text.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.open_page,
            ),
            ToolSpec(
                name="browser.extract_content",
                description="Extract structured text and metadata from the active or specified webpage.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.extract_content,
            ),
            ToolSpec(
                name="browser.summarize_page",
                description="Summarize readable content from an approved webpage with source citation.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.summarize_page,
            ),
            ToolSpec(
                name="browser.ask_page",
                description="Answer a user question grounded strictly in webpage text with source citation.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.ask_page,
            ),
            ToolSpec(
                name="browser.close_session",
                description="Close active browser instance and delete temporary profile directory.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.close_session,
            ),
            ToolSpec(
                name="browser.submit_form",
                description="Submit a web form (blocked in read-only MVP).",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.submit_form,
            ),
            ToolSpec(
                name="browser.download_file",
                description="Download a file from the web (blocked in read-only MVP).",
                risk_level=ToolRiskLevel.DANGEROUS,
                requires_confirmation=True,
                handler=self.download_file,
            ),
        ]

    # --- Legacy Handlers ---
    def open_site(self, site_name: str) -> ToolResult:
        res = self.browser.open_site(site_name)
        return ToolResult(status="SUCCESS", message=res, data={"site": site_name})

    def search_google(self, query: str) -> ToolResult:
        res = self.browser.search_google(query)
        return ToolResult(status="SUCCESS", message=res, data={"query": query})

    def search_github(self, query: str) -> ToolResult:
        res = self.browser.search_github(query)
        return ToolResult(status="SUCCESS", message=res, data={"query": query})

    def search_stackoverflow(self, query: str) -> ToolResult:
        res = self.browser.search_stackoverflow(query)
        return ToolResult(status="SUCCESS", message=res, data={"query": query})

    # --- Capability 4 Automation Handlers ---
    def open_page(self, url: str) -> ToolResult:
        nav = self.service.open_page(url)
        return ToolResult(
            status=nav.status,
            message=nav.message,
            data=nav.to_dict(),
            evidence={"url": nav.url, "title": nav.title, "length": nav.page.extracted_length if nav.page else 0},
            error=nav.error,
        )

    def extract_content(self, url: Optional[str] = None) -> ToolResult:
        if url and str(url).strip():
            nav = self.service.open_page(url.strip())
            if not nav.is_success or not nav.page:
                return ToolResult(status=nav.status, message=nav.message, error=nav.error)
            page = nav.page
        else:
            page = self.service.get_current_page()

        if not page:
            return ToolResult(status="FAILED", message="No active page content available.", error="NoActivePage")

        return ToolResult(
            status="VERIFIED",
            message=f"Extracted content from '{page.title}' ({page.url}).",
            data=page.to_dict(),
            evidence={"url": page.url, "extracted_length": page.extracted_length},
        )

    def summarize_page(self, url: Optional[str] = None) -> ToolResult:
        res = self.service.summarize_page(url=url)
        return ToolResult(
            status=res.status,
            message=res.message,
            data=res.to_dict(),
            evidence={"url": res.url, "title": res.title, "findings_count": len(res.key_findings)},
            error=res.message if res.status == "FAILED" else None,
        )

    def ask_page(self, question: str, url: Optional[str] = None) -> ToolResult:
        res = self.service.ask_page(question=question, url=url)
        return ToolResult(
            status=res.status,
            message=res.message,
            data=res.to_dict(),
            evidence={"url": res.source_url, "has_evidence": res.has_evidence, "citations": res.citations},
            error=res.message if res.status == "FAILED" else None,
        )

    def close_session(self) -> ToolResult:
        self.service.close_session()
        return ToolResult(
            status="VERIFIED",
            message="Browser session closed and ephemeral profile removed cleanly.",
            data={"closed": True},
            evidence={"driver_active": False},
        )

    def submit_form(self, form_data: Optional[dict] = None) -> ToolResult:
        return ToolResult(
            status="DENIED",
            message="Form submissions are disabled in read-only browser MVP for security.",
            error="SideEffectBlocked",
        )

    def download_file(self, url: Optional[str] = None) -> ToolResult:
        return ToolResult(
            status="DENIED",
            message="File downloads are disabled in read-only browser MVP for security.",
            error="SideEffectBlocked",
        )
