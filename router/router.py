"""Intent Router for OLIVER 2.0 with deterministic-first matching and schema-constrained LLM fallback."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from pydantic import BaseModel, Field

from core.config import get_config
from llm.provider import LLMProvider
from llm.ollama_provider import OllamaProvider
from skills.base import ToolResult, ToolRiskLevel, ToolSpec
from skills.builtin import register_all_builtin_skills
from skills.registry import SkillRegistry, get_registry

logger = logging.getLogger("oliver.router")


class IntentClassification(BaseModel):
    """Schema-constrained LLM output for intent routing."""

    skill_name: str = Field(description="Name of the target skill, e.g. 'windows', 'browser', 'ai'")
    tool_name: str = Field(description="Name of the tool, e.g. 'windows.open_app', 'ai.ask'")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Validated tool arguments")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    reasoning: Optional[str] = Field(default=None, description="Brief justification")


class RouteResult(BaseModel):
    """Result of intent routing."""

    matched: bool
    tool_name: Optional[str] = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    direct_response: Optional[str] = None
    requires_confirmation: bool = False
    risk_level: int = 0


class IntentRouter:
    """Routes user queries deterministically first, then via schema-constrained LLM."""

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        self.config = get_config()
        self.registry = registry or get_registry()
        # Ensure all builtins are loaded
        register_all_builtin_skills(self.registry)
        self.llm = llm_provider or OllamaProvider()

        # Build fast deterministic match table
        self._build_deterministic_rules()

    def _build_deterministic_rules(self) -> None:
        """Compile regexes and trigger lookup table for registered skills."""
        self.rules: list[tuple[re.Pattern, str, str]] = [
            # Windows apps
            (re.compile(r"^(?:open|launch|start|run)\s+(?:the\s+)?(notepad|calculator|calc|paint|explorer|vs\s*code|vscode|chrome|edge|firefox|cmd|command prompt|powershell|settings|task manager|control panel)$", re.IGNORECASE), "windows.open_app", "app_name"),
            # System workstation state
            (re.compile(r"^lock\s+(?:the\s+)?(?:computer|pc|workstation)$", re.IGNORECASE), "windows.lock_computer", ""),
            (re.compile(r"^restart\s+(?:windows\s+)?explorer$", re.IGNORECASE), "windows.restart_explorer", ""),
            (re.compile(r"^volume\s+(?:up|increase)$", re.IGNORECASE), "windows.volume_up", ""),
            (re.compile(r"^volume\s+(?:down|decrease)$", re.IGNORECASE), "windows.volume_down", ""),
            (re.compile(r"^mute(?:\s+volume)?$", re.IGNORECASE), "windows.mute", ""),
            (re.compile(r"^shut\s*down(?:\s+(?:the\s+)?(?:computer|pc))?$", re.IGNORECASE), "windows.shutdown", ""),
            (re.compile(r"^restart(?:\s+(?:the\s+)?(?:computer|pc))?$", re.IGNORECASE), "windows.restart", ""),
            (re.compile(r"^sleep(?:\s+(?:the\s+)?(?:computer|pc))?$", re.IGNORECASE), "windows.sleep", ""),

            # Browser & Search
            (re.compile(r"^(?:open|go to)\s+(?:the\s+)?(google|youtube|github|linkedin|flipkart|instagram|whatsapp|chatgpt)$", re.IGNORECASE), "browser.open_site", "site_name"),
            (re.compile(r"^search\s+(?:google\s+(?:for\s+)?)?(.+)$", re.IGNORECASE), "browser.search_google", "query"),
            (re.compile(r"^search\s+github\s+(?:for\s+)?(.+)$", re.IGNORECASE), "browser.search_github", "query"),
            (re.compile(r"^search\s+(?:stack\s*overflow|stackoverflow)\s+(?:for\s+)?(.+)$", re.IGNORECASE), "browser.search_stackoverflow", "query"),

            # YouTube
            (re.compile(r"^play\s+(.+)$", re.IGNORECASE), "youtube.play", "query"),
            (re.compile(r"^search\s+youtube\s+(?:for\s+)?(.+)$", re.IGNORECASE), "youtube.search", "query"),

            # Files
            (re.compile(r"^create\s+folder\s+(.+)$", re.IGNORECASE), "files.create_folder", "path"),
            (re.compile(r"^create\s+file\s+(.+)$", re.IGNORECASE), "files.create_file", "path"),
            (re.compile(r"^list\s+files(?:\s+in\s+(.+))?$", re.IGNORECASE), "files.list_folder", "path"),
            (re.compile(r"^open\s+(?:the\s+)?(desktop|documents|downloads|pictures|videos)\s+folder$", re.IGNORECASE), "files.open_folder", "path"),

            # Communication
            (re.compile(r"^send\s+whatsapp\s+message\s+to\s+(.+)$", re.IGNORECASE), "communication.whatsapp_prepare", "text"),
            (re.compile(r"^send\s+(?:an\s+)?email\s+to\s+(.+)$", re.IGNORECASE), "communication.email_prepare", "text"),

            # Productivity & Math
            (re.compile(r"^calculate\s+(.+)$", re.IGNORECASE), "productivity.calculate", "expression"),
            (re.compile(r"^remind\s+me\s+(?:to\s+)?(.+)$", re.IGNORECASE), "productivity.add_reminder", "title"),
            (re.compile(r"^(?:show|list)\s+reminders$", re.IGNORECASE), "productivity.list_reminders", ""),
            (re.compile(r"^start\s+stopwatch$", re.IGNORECASE), "productivity.start_stopwatch", ""),
            (re.compile(r"^stop\s+stopwatch$", re.IGNORECASE), "productivity.stop_stopwatch", ""),

            # Info
            (re.compile(r"^weather(?:\s+in\s+(.+))?$", re.IGNORECASE), "info.weather", "location"),
            (re.compile(r"^news(?:\s+(.+))?$", re.IGNORECASE), "info.news", "category"),
        ]

    def route(self, text: str) -> RouteResult:
        """Route user input to a tool specification."""
        clean_text = text.strip()
        if not clean_text:
            return RouteResult(matched=False, direct_response="Please provide a command.")

        # 1. Deterministic Rule Matching First
        for pattern, tool_name, arg_key in self.rules:
            match = pattern.match(clean_text)
            if match:
                args = {}
                if arg_key and match.groups():
                    val = match.group(1)
                    args[arg_key] = val.strip() if val else ""
                elif arg_key == "text":
                    args["text"] = clean_text

                tool = self.registry.get_tool(tool_name)
                return RouteResult(
                    matched=True,
                    tool_name=tool_name,
                    arguments=args,
                    confidence=1.0,
                    requires_confirmation=tool.requires_confirmation if tool else False,
                    risk_level=tool.risk_level.value if tool else 0,
                )

        # 2. Schema-Constrained LLM Intent Classification Fallback
        if self._is_potential_tool_command(clean_text):
            classification = self._classify_with_llm(clean_text)
            if classification and classification.confidence >= 0.7:
                tool = self.registry.get_tool(classification.tool_name)
                if tool:
                    return RouteResult(
                        matched=True,
                        tool_name=classification.tool_name,
                        arguments=classification.arguments,
                        confidence=classification.confidence,
                        requires_confirmation=tool.requires_confirmation,
                        risk_level=tool.risk_level.value,
                    )

        # 3. Default AI Q&A Fallback
        return RouteResult(
            matched=True,
            tool_name="ai.ask",
            arguments={"prompt": clean_text},
            confidence=0.8,
            risk_level=0,
        )

    def _is_potential_tool_command(self, text: str) -> bool:
        """Check if query looks like a command rather than general knowledge question."""
        lowered = text.lower()
        question_words = ["what is", "explain", "why is", "who is", "how does", "tell me about"]
        if any(lowered.startswith(w) for w in question_words):
            return False
        return len(text.split()) <= 12

    def _classify_with_llm(self, text: str) -> Optional[IntentClassification]:
        """Request structured intent classification from Ollama."""
        tools = self.registry.list_tools(only_enabled=True)
        tool_descriptions = "\n".join(f"- {t.name}: {t.description}" for t in tools[:20])

        prompt = (
            f"User request: '{text}'\n"
            f"Available tools:\n{tool_descriptions}\n"
            "Classify which tool best fits the user request and extract necessary arguments."
        )

        return self.llm.structured_output(
            prompt=prompt,
            schema=IntentClassification,
            system_prompt="You are OLIVER's intent classification engine.",
            max_retries=1,
        )

    def execute_route(self, route_res: RouteResult) -> str:
        """Execute the tool resolved by the route."""
        if not route_res.matched or not route_res.tool_name:
            return route_res.direct_response or "Could not determine action."

        tool = self.registry.get_tool(route_res.tool_name)
        if not tool or not tool.handler:
            return f"Tool '{route_res.tool_name}' is not available."

        try:
            result = tool.handler(**route_res.arguments)
            if isinstance(result, ToolResult):
                return result.message
            return str(result)
        except Exception as exc:
            logger.exception("Error executing tool %s: %s", route_res.tool_name, exc)
            return f"Execution error: {exc}"
