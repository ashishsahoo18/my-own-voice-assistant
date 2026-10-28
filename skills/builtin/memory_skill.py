"""Hybrid Memory Skill for OLIVER 2.0."""

from __future__ import annotations

from typing import Any
from memory.manager import get_memory_engine
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class MemorySkill(BaseSkill):
    """Adapter wrapping the OLIVER 2.0 Hybrid Memory Engine."""

    def __init__(self) -> None:
        super().__init__()
        self.engine = get_memory_engine()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="memory",
            version="1.0.0",
            description="Manage working, episodic, and semantic memory facts, preferences, and controls.",
            triggers=[
                "what do you remember",
                "remember that",
                "remember my",
                "forget this memory",
                "forget that",
                "memory status",
                "clear session memory",
            ],
            dependencies=["sqlite3"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="memory.what_do_you_remember",
                description="Show what OLIVER remembers about the user's facts and preferences.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.what_do_you_remember,
            ),
            ToolSpec(
                name="memory.remember",
                description="Store a new fact, rule, or preference in long-term memory.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.remember,
            ),
            ToolSpec(
                name="memory.forget",
                description="Delete a specific memory by ID or content phrase.",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.forget,
            ),
            ToolSpec(
                name="memory.status",
                description="Show memory storage status and statistics.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.status,
            ),
            ToolSpec(
                name="memory.clear_session",
                description="Clear active working conversation memory for the current session.",
                risk_level=ToolRiskLevel.LOW,
                handler=self.clear_session,
            ),
        ]

    def what_do_you_remember(self) -> ToolResult:
        res = self.engine.what_do_you_remember()
        return ToolResult(status="SUCCESS", message=res, data={"memories_overview": res})

    def remember(self, fact: str = "", content: str = "", category: str = "general") -> ToolResult:
        text = fact or content
        if not text.strip():
            return ToolResult(status="FAILED", message="Please specify what you would like me to remember.")

        success, msg = self.engine.remember(text.strip(), category=category)
        if success:
            return ToolResult(status="SUCCESS", message=f"Remembered: {text.strip()}", data={"fact": text.strip()})
        return ToolResult(status="DENIED", message=msg, error="PrivacyValidationFailed")

    def forget(self, target: str = "") -> ToolResult:
        res = self.engine.forget(target.strip())
        return ToolResult(status="SUCCESS", message=res, data={"target": target.strip()})

    def status(self) -> ToolResult:
        st = self.engine.status()
        msg = (
            f"OLIVER Memory Engine Active (WAL mode)\n"
            f"• Long-Term Memories: {st['total_semantic_memories']}\n"
            f"• Total Sessions: {st['total_sessions']}\n"
            f"• Total Stored Messages: {st['total_messages']}"
        )
        return ToolResult(status="SUCCESS", message=msg, data=st)

    def clear_session(self, session_id: str = "default") -> ToolResult:
        sid = session_id.strip() if session_id and session_id.strip() else "default"
        res = self.engine.clear_session_memory(sid)
        return ToolResult(status="SUCCESS", message=res, data={"session_id": sid})
