"""YouTube video search and direct playback skill for OLIVER 2.0."""

from __future__ import annotations

from commands.youtube import YouTubeCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class YouTubeSkill(BaseSkill):
    """Adapter wrapping YouTube search and direct playback commands."""

    def __init__(self) -> None:
        super().__init__()
        self.youtube = YouTubeCommands()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="youtube",
            version="1.0.0",
            description="Search YouTube videos and play music directly.",
            triggers=["play believer", "play ik mulaqaat", "search youtube for python tutorials"],
            dependencies=["webbrowser", "requests"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="youtube.search",
                description="Search YouTube without starting automatic playback.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.search,
            ),
            ToolSpec(
                name="youtube.play",
                description="Resolve video ID and start direct playback on YouTube.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.play,
            ),
        ]

    def search(self, query: str) -> ToolResult:
        res = self.youtube.search_youtube(query)
        return ToolResult(status="SUCCESS", message=res, data={"query": query})

    def play(self, query: str) -> ToolResult:
        res = self.youtube.play_youtube(query)
        return ToolResult(status="SUCCESS", message=res, data={"query": query})
