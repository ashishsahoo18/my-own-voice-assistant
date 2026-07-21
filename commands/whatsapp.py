from __future__ import annotations

import csv
import time
import webbrowser
from pathlib import Path
from typing import Optional

import pyautogui
import pywhatkit


class WhatsAppCommands:
    """Send WhatsApp messages using WhatsApp Web."""

    def __init__(self, contacts_path: Optional[str] = None) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.contacts_path = Path(contacts_path) if contacts_path else project_root / "contacts.csv"

    def open_whatsapp(self) -> str:
        """Open WhatsApp Web."""
        webbrowser.open("https://web.whatsapp.com")
        return "Opened WhatsApp Web."

    def send_message(self, number: str, message: str) -> str:
        """Send a WhatsApp message directly."""
        clean_number = self._clean_number(number)
        clean_message = message.strip()

        if not clean_number:
            return "Please provide a WhatsApp number."
        if not clean_message:
            return "Please provide a message to send."

        try:
            pywhatkit.sendwhatmsg_instantly(
                phone_no=f"+{clean_number}",
                message=clean_message,
                wait_time=25,
                tab_close=False,
                close_time=3,
            )

            time.sleep(3)
            pyautogui.press("enter")

            return f"Sent WhatsApp message to {clean_number}."
        except Exception as exc:
            return f"Could not send WhatsApp message: {exc}"

    def send_to_contact(self, contact_name: str, message: str) -> str:
        """Send a WhatsApp message to a saved contact."""
        contacts = self._load_contacts()
        number = contacts.get(contact_name.lower().strip())

        if not number:
            return f"Contact not found: {contact_name}"

        return self.send_message(number, message)

    def _load_contacts(self) -> dict[str, str]:
        """Load contacts from contacts.csv."""
        if not self.contacts_path.exists():
            return {}

        contacts: dict[str, str] = {}

        with self.contacts_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                name = (row.get("name") or "").lower().strip()
                number = self._clean_number(row.get("number") or "")

                if name and number:
                    contacts[name] = number

        return contacts

    def _clean_number(self, number: str) -> str:
        """Keep only digits from the phone number."""
        return "".join(char for char in number if char.isdigit())