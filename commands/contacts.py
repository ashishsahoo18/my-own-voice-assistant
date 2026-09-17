"""Contact management module for ASHISH AI."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Contact:
    name: str
    phone: str
    email: str


@dataclass
class ContactQueryResult:
    found: bool = False
    is_ambiguous: bool = False
    contact: Optional[Contact] = None
    matches: list[Contact] = None
    error_message: str = ""

    def __post_init__(self) -> None:
        if self.matches is None:
            self.matches = []


class ContactManager:
    """Load and query contacts safely with ambiguity detection."""

    def __init__(self, contacts_path: Optional[str] = None) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.contacts_path = Path(contacts_path) if contacts_path else project_root / "contacts.csv"

    def load_contacts(self) -> list[Contact]:
        """Load contacts list from contacts.csv."""
        if not self.contacts_path.exists():
            return []

        contacts: list[Contact] = []
        try:
            with self.contacts_path.open("r", encoding="utf-8", newline="") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    name = (row.get("name") or "").strip()
                    phone = (row.get("number") or row.get("phone") or "").strip()
                    email = (row.get("email") or "").strip()
                    if name:
                        contacts.append(Contact(name=name, phone=phone, email=email))
        except Exception:
            pass
        return contacts

    def resolve_contact(self, name_query: str) -> ContactQueryResult:
        """Resolve contact query. Asks for clarification if ambiguous."""
        query = name_query.strip().lower()
        if not query:
            return ContactQueryResult(error_message="Please specify a contact name.")

        all_contacts = self.load_contacts()
        if not all_contacts:
            return ContactQueryResult(error_message=f"No contacts found in contacts list for '{name_query}'.")

        # 1. Exact match (case insensitive)
        exact_matches = [c for c in all_contacts if c.name.lower() == query]
        if len(exact_matches) == 1:
            return ContactQueryResult(found=True, contact=exact_matches[0])
        elif len(exact_matches) > 1:
            match_str = ", ".join(f"{c.name} ({c.phone or c.email})" for c in exact_matches)
            return ContactQueryResult(
                is_ambiguous=True,
                matches=exact_matches,
                error_message=f"Which '{name_query}' do you mean? Available matching contacts: {match_str}",
            )

        # 2. Substring match
        sub_matches = [c for c in all_contacts if query in c.name.lower() or c.name.lower() in query]
        if len(sub_matches) == 1:
            return ContactQueryResult(found=True, contact=sub_matches[0])
        elif len(sub_matches) > 1:
            match_str = ", ".join(f"{c.name} ({c.phone or c.email})" for c in sub_matches)
            return ContactQueryResult(
                is_ambiguous=True,
                matches=sub_matches,
                error_message=f"Which '{name_query}' do you mean? Available matching contacts: {match_str}",
            )

        return ContactQueryResult(
            error_message=f"Contact not found for '{name_query}'. Please specify phone number/email or add to contacts."
        )
