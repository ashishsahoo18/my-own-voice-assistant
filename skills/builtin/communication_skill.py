"""WhatsApp and Email communication skill for OLIVER 2.0."""

from __future__ import annotations

from typing import Optional
from commands.contacts import ContactManager
from commands.email_service import EmailService
from commands.whatsapp import WhatsAppCommands
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec


class CommunicationSkill(BaseSkill):
    """Adapter wrapping WhatsApp messaging and Email service."""

    def __init__(self, contact_manager: Optional[ContactManager] = None) -> None:
        super().__init__()
        self.contacts = contact_manager or ContactManager()
        self.whatsapp = WhatsAppCommands(self.contacts)
        self.email_service = EmailService(self.contacts)

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="communication",
            version="1.0.0",
            description="Send WhatsApp messages and dispatch emails with confirmation safety.",
            triggers=["send whatsapp message to", "send an email to"],
            dependencies=["smtplib", "webbrowser"],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="communication.whatsapp_prepare",
                description="Parse WhatsApp command and prepare confirmation payload.",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.whatsapp_prepare,
            ),
            ToolSpec(
                name="communication.whatsapp_send",
                description="Send confirmed WhatsApp message.",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.whatsapp_send,
            ),
            ToolSpec(
                name="communication.email_prepare",
                description="Parse Email command and prepare confirmation payload.",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.email_prepare,
            ),
            ToolSpec(
                name="communication.email_send",
                description="Send confirmed email via SMTP or web compose.",
                risk_level=ToolRiskLevel.SENSITIVE,
                requires_confirmation=True,
                handler=self.email_send,
            ),
        ]

    def whatsapp_prepare(self, text: str) -> ToolResult:
        res = self.whatsapp.prepare_whatsapp_command(text)
        return ToolResult(status="SUCCESS", message=res)

    def whatsapp_send(self, number: str, message: str) -> ToolResult:
        res = self.whatsapp.send_message(number, message)
        # Note: WhatsApp delivery is unverified
        status = "UNVERIFIED" if "Sent WhatsApp message" in res else "FAILED"
        return ToolResult(status=status, message=res, data={"recipient": number})

    def email_prepare(self, text: str) -> ToolResult:
        res = self.email_service.prepare_email_command(text)
        return ToolResult(status="SUCCESS", message=res)

    def email_send(self, to_email: str, subject: str, message: str) -> ToolResult:
        res = self.email_service.send_email(to_email, subject, message)
        status = "SUCCESS" if "Email sent successfully" in res else "UNVERIFIED"
        return ToolResult(status=status, message=res, data={"recipient": to_email})
