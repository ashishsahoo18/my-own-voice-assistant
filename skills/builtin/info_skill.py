"""Weather and news informational skill for OLIVER 2.0."""

from __future__ import annotations

from commands.news import NewsCommands
from commands.weather import WeatherCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class InfoSkill(BaseSkill):
    """Adapter wrapping Weather and News API queries."""

    def __init__(self) -> None:
        super().__init__()
        self.weather = WeatherCommands()
        self.news = NewsCommands()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="info",
            version="1.0.0",
            description="Fetch live weather forecasts and current news headlines.",
            triggers=["weather in", "latest news", "news technology"],
            dependencies=["urllib"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="info.weather",
                description="Get weather forecast for a specified city or location.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.get_weather,
            ),
            ToolSpec(
                name="info.news",
                description="Get news headlines for a category.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.get_news,
            ),
        ]

    def get_weather(self, location: str = "Delhi") -> ToolResult:
        res = self.weather.get_weather(location)
        return ToolResult(status="SUCCESS", message=res, data={"location": location})

    def get_news(self, category: str = "technology") -> ToolResult:
        res = self.news.get_news(category)
        return ToolResult(status="SUCCESS", message=res, data={"category": category})
