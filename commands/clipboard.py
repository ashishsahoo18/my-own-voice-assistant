"""Clipboard commands for AYRA AI."""

from __future__ import annotations


class ClipboardCommands:
    """Clipboard helpers for copying, pasting, and viewing content."""

    def copy_text(self, text: str) -> str:
        """Copy text to clipboard."""
        clean_text = text.strip()

        if not clean_text:
            return "Please provide text to copy."

        try:
            import pyperclip

            pyperclip.copy(clean_text)
            return "Copied text to clipboard."
        except Exception as exc:
            return f"Could not copy text. Install pyperclip if needed. Details: {exc}"

    def paste_text(self) -> str:
        """Return clipboard text."""
        try:
            import pyperclip

            clipboard_text = pyperclip.paste()
        except Exception as exc:
            return f"Could not read clipboard. Install pyperclip if needed. Details: {exc}"

        if not clipboard_text:
            return "Clipboard is empty."

        return self._preview_text(clipboard_text)

    def clear_clipboard(self) -> str:
        """Clear clipboard text."""
        try:
            import pyperclip

            pyperclip.copy("")
            return "Cleared clipboard."
        except Exception as exc:
            return f"Could not clear clipboard. Install pyperclip if needed. Details: {exc}"

    def view_clipboard(self) -> str:
        """Show clipboard preview."""
        return self.paste_text()

    def _preview_text(self, text: str, max_chars: int = 1200) -> str:
        """Return a safe clipboard preview."""
        clean_text = text.strip()

        if len(clean_text) <= max_chars:
            return clean_text

        return clean_text[:max_chars].rstrip() + "\n\n[Clipboard preview truncated.]"