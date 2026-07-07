from __future__ import annotations

import subprocess
from typing import Optional


class ClipboardCommands:
    """Clipboard helpers for copying, pasting, and viewing content."""

    def copy_text(self, text: str) -> str:
        try:
            import pyperclip
            pyperclip.copy(text)
            return "Copied text to clipboard."
        except Exception as exc:
            return f"Could not copy text: {exc}"

    def paste_text(self) -> str:
        try:
            import pyperclip
            return pyperclip.paste()
        except Exception as exc:
            return f"Could not read clipboard: {exc}"

    def clear_clipboard(self) -> str:
        try:
            import pyperclip
            pyperclip.copy("")
            return "Cleared clipboard."
        except Exception as exc:
            return f"Could not clear clipboard: {exc}"

    def view_clipboard(self) -> str:
        return self.paste_text()
