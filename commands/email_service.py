"""Gmail and Email Service module for ASHISH AI."""

from __future__ import annotations

import os
import re
import smtplib
import urllib.parse
import webbrowser
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from commands.contacts import ContactManager, ContactQueryResult

try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
except ImportError:
    pass


class EmailService:
    """Handle email preparation, contact email resolution, confirmation, and sending."""

    def __init__(self, contact_manager: Optional[ContactManager] = None) -> None:
        self.contacts = contact_manager or ContactManager()

    def prepare_email_command(self, text: str) -> str:
        """Parse email command and prepare confirmation string or error."""
        recipient_query, subject, message = self._parse_email_text(text)

        if not recipient_query:
            return "Please specify a recipient for the email."

        if not message:
            return "Please specify the message for the email."

        # Check if recipient_query is a raw email address
        if "@" in recipient_query and "." in recipient_query:
            email_address = recipient_query
            display_name = recipient_query.split("@")[0]
        else:
            res: ContactQueryResult = self.contacts.resolve_contact(recipient_query)
            if res.is_ambiguous or not res.found:
                return res.error_message
            if not res.contact.email:
                return f"No email address found for contact '{res.contact.name}'. Please add an email address or specify one."
            display_name = res.contact.name
            email_address = res.contact.email

        # Format confirmation string payload
        return f"CONFIRMATION_REQUIRED:EMAIL:{display_name}|{email_address}|{subject}|{message}"

    def send_email(self, to_email: str, subject: str, message: str) -> str:
        """Send email via SMTP if credentials exist in .env, else open Gmail web compose link."""
        sender_email = os.getenv("GMAIL_SENDER_EMAIL", "").strip()
        app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

        clean_to = to_email.strip()
        clean_subj = subject.strip() or "Message from ASHISH AI"
        clean_msg = message.strip()

        if not clean_to:
            return "Please specify a recipient email address."

        if sender_email and app_password:
            try:
                msg = MIMEText(clean_msg, "plain", "utf-8")
                msg["Subject"] = clean_subj
                msg["From"] = sender_email
                msg["To"] = clean_to

                with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                    server.login(sender_email, app_password)
                    server.send_message(msg)

                return f"Email sent successfully to {clean_to}."
            except Exception as exc:
                return f"EMAIL SERVICE ERROR: Could not send email via SMTP ({exc})."

        # Web compose fallback if SMTP credentials not configured
        try:
            encoded_to = urllib.parse.quote(clean_to)
            encoded_su = urllib.parse.quote(clean_subj)
            encoded_body = urllib.parse.quote(clean_msg)
            web_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={encoded_to}&su={encoded_su}&body={encoded_body}"
            
            webbrowser.open(web_url)
            return "GMAIL OPENED — EMAIL NOT SENT"
        except Exception as exc:
            return f"EMAIL SERVICE ERROR: Could not open Gmail in browser: {exc}"

    def _parse_email_text(self, text: str) -> tuple[str, str, str]:
        """Extract recipient, subject, and message from command prompt."""
        # e.g. "Send an email to Rahul with subject Project Update saying the project is completed"
        subject = "Message from ASHISH AI"
        recipient = ""
        message = ""

        # Check for subject
        subj_match = re.search(r"with subject\s+['\"]?(.+?)['\"]?\s+(?:saying|that|with message)\s+(.+)", text, flags=re.IGNORECASE)
        if subj_match:
            subject = subj_match.group(1).strip()
            message = subj_match.group(2).strip()
            # Extract recipient before subject
            prefix = text[:subj_match.start()]
            rec_match = re.search(r"(?:email|to)\s+(.+)", prefix, flags=re.IGNORECASE)
            if rec_match:
                recipient = rec_match.group(1).strip()
            return recipient, subject, message

        # Standard: "Send an email to Rahul saying the meeting is at 5 PM"
        to_say_match = re.search(r"(?:email|to)\s+(.+?)\s+(?:saying|that|message)\s+(.+)", text, flags=re.IGNORECASE)
        if to_say_match:
            recipient = to_say_match.group(1).strip()
            message = to_say_match.group(2).strip()
            return recipient, subject, message

        # Simple: "Send an email to Rahul"
        to_match = re.search(r"(?:email|to)\s+(.+)", text, flags=re.IGNORECASE)
        if to_match:
            recipient = to_match.group(1).strip()

        return recipient, subject, message
