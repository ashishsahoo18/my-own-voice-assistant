from __future__ import annotations

import webbrowser


class WhatsAppCommands:
    """WhatsApp Web helpers for the assistant."""

    def open_whatsapp(self) -> str:
        webbrowser.open("https://web.whatsapp.com")
        return "Opened WhatsApp Web."

    def send_message(self, contact: str, message: str) -> str:
        return f"Prepared to send '{message}' to {contact}."

    def search_contact(self, contact: str) -> str:
        return f"Searching for {contact} in WhatsApp."
