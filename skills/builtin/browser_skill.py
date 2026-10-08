"""Web browser navigation and search skill for OLIVER 2.0."""

from __future__ import annotations

from commands.browser import BrowserCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class BrowserSkill(BaseSkill):
    """Adapter wrapping web browser shortcuts and web searching."""

    def __init__(self) -> None:
        super().__init__()
        self.browser = BrowserCommands()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="browser",
            version="1.0.0",
            description="Open websites, launch social and work tools, and perform web searches.",
            triggers=[
                "open google", "open youtube", "open github", "open linkedin",
                "open flipkart", "search google for", "search github for",
            ],
            dependencies=["webbrowser"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="browser.open_site",
                description="Open a recognized website or URL in the default browser.",
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
        ]

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
