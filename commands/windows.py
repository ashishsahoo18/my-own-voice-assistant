"""Windows desktop automation commands for AYRA AI."""

from __future__ import annotations

import ctypes
import os
import subprocess


class WindowsCommands:
    """Safe Windows desktop automation helpers."""

    def __init__(self) -> None:
        self._confirmations = {
            "delete": "Delete operation requires confirmation.",
            "shutdown": "Shutdown requires confirmation.",
            "restart": "Restart requires confirmation.",
            "empty recycle bin": "Empty recycle bin requires confirmation.",
        }

        self.apps = {
            "notepad": "notepad.exe",
            "vscode": "code",
            "vs code": "code",
            "visual studio code": "code",
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "paint": "mspaint.exe",
            "file explorer": "explorer.exe",
            "explorer": "explorer.exe",
            "task manager": "taskmgr.exe",
            "control panel": "control.exe",
            "command prompt": "cmd.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "settings": "ms-settings:",
        }

    def open_app(self, app_name: str) -> str:
        """Open a supported Windows application."""
        clean_name = app_name.strip().lower()

        if not clean_name:
            return "Which Windows app should I open?"

        command = self.apps.get(clean_name)

        if not command:
            return f"I do not support opening {app_name} yet."

        try:
            if command.startswith("ms-settings:"):
                os.startfile(command)
            else:
                subprocess.Popen([command])

            return f"Opened {app_name}."
        except Exception as exc:
            return f"Could not open {app_name}: {exc}"

    def lock_computer(self) -> str:
        """Lock the Windows workstation."""
        try:
            ctypes.windll.user32.LockWorkStation()
            return "Locked the computer."
        except Exception as exc:
            return f"Could not lock the computer: {exc}"

    def restart_explorer(self) -> str:
        """Restart Windows Explorer."""
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "explorer.exe"],
                check=False,
                capture_output=True,
                text=True,
            )
            subprocess.Popen(["explorer.exe"])
            return "Restarted Explorer."
        except Exception as exc:
            return f"Could not restart Explorer: {exc}"

    def empty_recycle_bin(self) -> str:
        """Require confirmation before emptying recycle bin."""
        return self.confirm_action("empty recycle bin")

    def shutdown(self) -> str:
        """Require confirmation before shutdown."""
        return self.confirm_action("shutdown")

    def restart(self) -> str:
        """Require confirmation before restart."""
        return self.confirm_action("restart")

    def confirm_action(self, action: str) -> str:
        """Return confirmation message for sensitive actions."""
        clean_action = action.strip().lower()
        return self._confirmations.get(
            clean_action,
            f"{clean_action.title()} requires confirmation.",
        )