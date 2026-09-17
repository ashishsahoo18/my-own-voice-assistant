"""WhatsApp automation commands for ASHISH AI."""

from __future__ import annotations

import re
import time
import webbrowser
from typing import Optional
from urllib.parse import quote

from commands.contacts import ContactManager, ContactQueryResult

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pywhatkit
except Exception:
    pywhatkit = None


class WhatsAppCommands:
    """Send WhatsApp messages using WhatsApp Web and Desktop protocols."""

    def __init__(self, contact_manager: Optional[ContactManager] = None) -> None:
        self.contacts = contact_manager or ContactManager()

    def open_whatsapp(self) -> str:
        """Open WhatsApp Web."""
        try:
            if not webbrowser.open("https://web.whatsapp.com"):
                return "Could not open WhatsApp Web in the default browser."
            return "Opening WhatsApp Web."
        except Exception:
            return "Could not open WhatsApp Web in the default browser."

    def prepare_whatsapp_command(self, text: str) -> str:
        """Parse WhatsApp command and prepare confirmation payload or error message."""
        recipient_query, message = self._parse_whatsapp_text(text)

        if not recipient_query:
            return "Please specify a recipient for the WhatsApp message."

        if not message:
            return "What message would you like to send on WhatsApp?"

        # Check if recipient_query is a raw phone number
        digits = "".join(c for c in recipient_query if c.isdigit())
        if len(digits) >= 10:
            phone_number = self._clean_number(digits)
            display_name = recipient_query
        else:
            res: ContactQueryResult = self.contacts.resolve_contact(recipient_query)
            if res.is_ambiguous or not res.found:
                return res.error_message
            if not res.contact.phone:
                return f"No phone number found for contact '{res.contact.name}'."
            display_name = res.contact.name
            phone_number = self._clean_number(res.contact.phone)

        return f"CONFIRMATION_REQUIRED:WHATSAPP:{display_name}|{phone_number}|{message}"

    def send_message(self, number: str, message: str) -> str:
        """Send a WhatsApp message directly after user confirmation."""
        clean_number = self._clean_number(number)
        clean_message = message.strip()

        if not clean_number:
            return "Please provide a WhatsApp number."
        if not clean_message:
            return "Please provide a message to send."

        try:
            whatsapp_url = f"https://web.whatsapp.com/send?phone={clean_number}&text={quote(clean_message)}"
            opened = webbrowser.open(whatsapp_url)
            if not opened:
                return "Could not open WhatsApp Web in the default browser."

            if pyautogui is not None:
                time.sleep(4)
                pyautogui.press("enter")
                return f"Sent WhatsApp message to +{clean_number}."
            else:
                return "OPENED — MESSAGE NOT SENT"
        except Exception:
            try:
                if pywhatkit is None or pyautogui is None:
                    return "OPENED — MESSAGE NOT SENT"
                pywhatkit.sendwhatmsg_instantly(
                    phone_no=f"+{clean_number}",
                    message=clean_message,
                    wait_time=20,
                    tab_close=False,
                    close_time=3,
                )
                time.sleep(2)
                pyautogui.press("enter")
                return f"Sent WhatsApp message to +{clean_number}."
            except Exception as exc:
                return f"Could not send WhatsApp message: {exc}"

    def send_to_contact(self, contact_name: str, message: str) -> str:
        """Send a WhatsApp message to a saved contact."""
        res = self.contacts.resolve_contact(contact_name)
        if res.is_ambiguous or not res.found:
            return res.error_message
        if not res.contact.phone:
            return f"No phone number found for contact '{res.contact.name}'."
        return self.send_message(res.contact.phone, message)

    def _parse_whatsapp_text(self, text: str) -> tuple[str, str]:
        """Extract recipient and message from prompt."""
        clean = re.sub(r"^(?:send\s+a?\s*whatsapp\s+message|send\s+whatsapp\s+message|send\s+whatsapp|message)\s+", "", text, flags=re.IGNORECASE).strip()

        to_say_match = re.search(r"^(?:to\s+)?(.+?)\s+(?:saying|that|message)\s+(.+)", clean, flags=re.IGNORECASE)
        if to_say_match:
            return to_say_match.group(1).strip(), to_say_match.group(2).strip()

        to_match = re.search(r"^(?:to\s+)?(.+)", clean, flags=re.IGNORECASE)
        if to_match:
            return to_match.group(1).strip(), ""

        return "", ""

    def _clean_number(self, number: str) -> str:
        """Keep only digits and auto-add 91 for 10-digit Indian numbers."""
        digits = "".join(char for char in number if char.isdigit())
        if len(digits) == 10:
            digits = "91" + digits
        return digits
