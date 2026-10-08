"""Address book and contact management skill for OLIVER 2.0."""

from __future__ import annotations

from typing import Optional
from commands.contacts import ContactManager
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class ContactsSkill(BaseSkill):
    """Adapter wrapping ContactManager ambiguity resolution."""

    def __init__(self, contacts_path: Optional[str] = None) -> None:
        super().__init__()
        self.contacts = ContactManager(contacts_path)

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="contacts",
            version="1.0.0",
            description="Lookup contacts, resolve ambiguous names, and read address book.",
            triggers=["resolve contact", "find contact"],
            dependencies=["csv"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="contacts.resolve",
                description="Resolve a contact query safely with ambiguity detection.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.resolve_contact,
            ),
            ToolSpec(
                name="contacts.list",
                description="List all available contact names in address book.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.list_contacts,
            ),
        ]

    def resolve_contact(self, name: str) -> ToolResult:
        res = self.contacts.resolve_contact(name)
        if res.is_ambiguous:
            return ToolResult(
                status="FAILED",
                message=res.error_message,
                data={"is_ambiguous": True, "matches": [c.name for c in res.matches]},
            )
        if not res.found:
            return ToolResult(status="FAILED", message=res.error_message, data={"found": False})

        return ToolResult(
            status="SUCCESS",
            message=f"Contact found: {res.contact.name}",
            data={"name": res.contact.name, "phone": res.contact.phone, "email": res.contact.email},
        )

    def list_contacts(self) -> ToolResult:
        contacts = self.contacts.load_contacts()
        names = [c.name for c in contacts]
        return ToolResult(status="SUCCESS", message=f"{len(names)} contacts loaded.", data={"contacts": names})
