"""Builtin skills package for OLIVER 2.0."""

from __future__ import annotations

from skills.builtin.ai_skill import AISkill
from skills.builtin.browser_skill import BrowserSkill
from skills.builtin.communication_skill import CommunicationSkill
from skills.builtin.contacts_skill import ContactsSkill
from skills.builtin.files_skill import FilesSkill
from skills.builtin.info_skill import InfoSkill
from skills.builtin.productivity_skill import ProductivitySkill
from skills.builtin.windows_skill import WindowsSkill
from skills.builtin.youtube_skill import YouTubeSkill
from skills.registry import SkillRegistry, get_registry


def register_all_builtin_skills(registry: SkillRegistry | None = None) -> SkillRegistry:
    """Instantiate and register all builtin skills."""
    reg = registry or get_registry()

    builtin_classes = [
        WindowsSkill,
        BrowserSkill,
        YouTubeSkill,
        FilesSkill,
        CommunicationSkill,
        ContactsSkill,
        InfoSkill,
        ProductivitySkill,
        AISkill,
    ]

    for cls in builtin_classes:
        try:
            skill = cls()
            reg.register(skill)
        except Exception:
            pass

    return reg
