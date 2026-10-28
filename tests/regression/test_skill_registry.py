"""Unit tests for OLIVER 2.0 SkillRegistry and BaseSkill architecture."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skills.base import (
    BaseSkill,
    SkillManifest,
    ToolResult,
    ToolRiskLevel,
    ToolSpec,
)
from skills.builtin import register_all_builtin_skills
from skills.registry import SkillRegistry


class DummySkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="dummy",
            version="1.0.0",
            description="Dummy skill for testing",
            triggers=["dummy test"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="dummy.echo",
                description="Echo input text",
                risk_level=ToolRiskLevel.SAFE,
                handler=lambda text="": ToolResult(status="SUCCESS", message=f"Echo: {text}"),
            )
        ]


class BrokenSkill(BaseSkill):
    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="broken",
            description="Broken skill that fails health check",
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="broken.tool",
                description="Tool that should not run",
                handler=lambda: ToolResult(status="FAILED", message="Broken"),
            )
        ]

    def health_check(self) -> tuple[bool, str]:
        return False, "Missing external binary: dummy_tool.exe"


class SkillRegistryTests(unittest.TestCase):
    """Test registry operations, health checks, and broken-skill isolation."""

    def setUp(self) -> None:
        self.registry = SkillRegistry()

    def test_register_and_lookup_tool(self) -> None:
        skill = DummySkill()
        success = self.registry.register(skill)
        self.assertTrue(success)

        tool = self.registry.get_tool("dummy.echo")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "dummy.echo")

        # Execute handler
        result = tool.handler(text="Hello")
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.message, "Echo: Hello")

    def test_broken_skill_isolation(self) -> None:
        """Broken skills are registered as disabled without raising uncaught exceptions."""
        broken = BrokenSkill()
        success = self.registry.register(broken)
        self.assertTrue(success, "Registry should handle broken skills cleanly")

        skill = self.registry.get_skill("broken")
        self.assertIsNotNone(skill)
        self.assertFalse(skill.enabled, "Broken skill must be disabled")

        # Tool should not appear in active tools list
        active_tools = [t.name for t in self.registry.list_tools(only_enabled=True)]
        self.assertNotIn("broken.tool", active_tools)

    def test_enable_disable_skill(self) -> None:
        skill = DummySkill()
        self.registry.register(skill)
        self.assertTrue(skill.enabled)

        self.registry.disable_skill("dummy")
        self.assertFalse(skill.enabled)

        self.registry.enable_skill("dummy")
        self.assertTrue(skill.enabled)

    def test_builtin_skills_loading(self) -> None:
        """Verify all 9 builtin skills register properly."""
        reg = SkillRegistry()
        register_all_builtin_skills(reg)

        skills = [s["name"] for s in reg.list_skills()]
        expected = ["windows", "browser", "youtube", "files", "communication", "contacts", "info", "productivity", "ai"]
        for exp in expected:
            self.assertIn(exp, skills, f"Builtin skill '{exp}' must be registered")

        tools = [t.name for t in reg.list_tools()]
        self.assertIn("windows.open_app", tools)
        self.assertIn("browser.open_site", tools)
        self.assertIn("youtube.play", tools)
        self.assertIn("files.create_folder", tools)
        self.assertIn("productivity.calculate", tools)

    def test_user_skills_discovery(self) -> None:
        """Test drop-in user skill discovery from a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            skill_folder = tmppath / "hello_skill"
            skill_folder.mkdir()

            code = '''
from skills.base import BaseSkill, SkillManifest, ToolSpec, ToolResult

class HelloSkill(BaseSkill):
    def get_manifest(self):
        return SkillManifest(name="hello", description="Drop-in skill")
    def get_tools(self):
        return [ToolSpec(name="hello.greet", description="Say hi", handler=lambda: ToolResult(message="Hi!"))]

def get_skill():
    return HelloSkill()
'''
            (skill_folder / "__init__.py").write_text(code, encoding="utf-8")

            count = self.registry.discover_user_skills(tmppath)
            self.assertEqual(count, 1)
            self.assertIsNotNone(self.registry.get_tool("hello.greet"))


if __name__ == "__main__":
    unittest.main()
