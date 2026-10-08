"""Central skill registry for discovering, validating, and managing OLIVER 2.0 skills."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Optional

from skills.base import BaseSkill, SkillManifest, ToolSpec

logger = logging.getLogger("oliver.skills.registry")


class SkillRegistry:
    """Manages skill registration, validation, health checking, and tool resolution."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._tools: dict[str, ToolSpec] = {}
        self._health_status: dict[str, tuple[bool, str]] = {}

    def register(self, skill: BaseSkill) -> bool:
        """Register and validate a skill and its tools with broken-skill isolation."""
        try:
            manifest = skill.get_manifest()
            if not manifest or not manifest.name:
                logger.error("Skill rejected: missing or invalid manifest.")
                return False

            name = manifest.name.strip().lower()

            # Health check before activating
            is_healthy, health_msg = skill.health_check()
            self._health_status[name] = (is_healthy, health_msg)

            if not is_healthy:
                logger.warning(
                    "Skill '%s' failed health check (%s); registered as disabled.",
                    name,
                    health_msg,
                )
                skill.enabled = False

            # Register tools
            tools = skill.get_tools()
            for tool in tools:
                tool_key = tool.name.strip().lower()
                self._tools[tool_key] = tool

            self._skills[name] = skill
            logger.info("Registered skill '%s' with %d tool(s). Status: %s", name, len(tools), health_msg)
            return True

        except Exception as exc:
            logger.exception("Failed to register skill '%s': %s", getattr(skill, "__class__", type(skill)), exc)
            return False

    def unregister(self, name: str) -> bool:
        """Unregister a skill and remove its tools."""
        key = name.strip().lower()
        if key not in self._skills:
            return False

        skill = self._skills.pop(key)
        self._health_status.pop(key, None)

        try:
            for tool in skill.get_tools():
                self._tools.pop(tool.name.strip().lower(), None)
        except Exception:
            pass

        return True

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """Retrieve skill instance by name."""
        return self._skills.get(name.strip().lower())

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """Retrieve tool specification by tool name."""
        return self._tools.get(name.strip().lower())

    def enable_skill(self, name: str) -> bool:
        """Enable an existing registered skill."""
        skill = self.get_skill(name)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable_skill(self, name: str) -> bool:
        """Disable a registered skill."""
        skill = self.get_skill(name)
        if skill:
            skill.enabled = False
            return True
        return False

    def list_skills(self) -> list[dict]:
        """Return list of registered skills with health and activation status."""
        result = []
        for name, skill in self._skills.items():
            manifest = skill.get_manifest()
            is_healthy, msg = self._health_status.get(name, (False, "Unknown"))
            result.append({
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "enabled": skill.enabled,
                "healthy": is_healthy,
                "status_message": msg,
                "tools_count": len(skill.get_tools()),
            })
        return result

    def list_tools(self, only_enabled: bool = True) -> list[ToolSpec]:
        """Return list of all registered tools."""
        if not only_enabled:
            return list(self._tools.values())

        active_tools = []
        for tool in self._tools.values():
            # Find owning skill
            skill_prefix = tool.name.split(".")[0].lower()
            skill = self.get_skill(skill_prefix)
            if skill and skill.enabled:
                active_tools.append(tool)
            elif not skill:
                active_tools.append(tool)
        return active_tools

    def discover_user_skills(self, user_skills_dir: Path) -> int:
        """Discover and load drop-in user skills from external folder."""
        if not user_skills_dir.exists() or not user_skills_dir.is_dir():
            return 0

        loaded_count = 0
        for entry in user_skills_dir.iterdir():
            if entry.is_dir() and (entry / "__init__.py").exists():
                try:
                    spec = importlib.util.spec_from_file_location(entry.name, entry / "__init__.py")
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, "get_skill"):
                            skill_inst = module.get_skill()
                            if isinstance(skill_inst, BaseSkill):
                                if self.register(skill_inst):
                                    loaded_count += 1
                except Exception as exc:
                    logger.warning("Could not load user skill from %s: %s", entry, exc)

        return loaded_count


_default_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """Return the global skill registry instance."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SkillRegistry()
    return _default_registry
