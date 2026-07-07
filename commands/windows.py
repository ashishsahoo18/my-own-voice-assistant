from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


class WindowsCommands:
    """Safe Windows desktop automation helpers."""

    def __init__(self) -> None:
        self._confirmations = {
            "delete": "Delete operation requires confirmation.",
            "shutdown": "Shutdown requires confirmation.",
        }

    def open_app(self, app_name: str) -> str:
        apps = {
            "notepad": ["notepad.exe"],
            "vscode": ["code"],
            "visual studio code": ["code"],
            "chrome": ["chrome"],
            "edge": ["msedge"],
            "calculator": ["calc"],
            "paint": ["mspaint"],
            "file explorer": ["explorer.exe"],
            "explorer": ["explorer.exe"],
            "task manager": ["taskmgr"],
            "control panel": ["control"],
            "command prompt": ["cmd"],
            "powershell": ["powershell"],
            "settings": ["ms-settings:"],
        }
        command = apps.get(app_name.lower())
        if not command:
            return f"I don't support opening {app_name} yet."
        try:
            subprocess.Popen(command)
            return f"Opened {app_name}."
        except Exception as exc:
            return f"Could not open {app_name}: {exc}"

    def lock_computer(self) -> str:
        try:
            os.system("rundll32.exe user32.dll,LockWorkStation")
            return "Locked the computer."
        except Exception as exc:
            return f"Could not lock the computer: {exc}"

    def restart_explorer(self) -> str:
        try:
            subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], check=False)
            subprocess.Popen(["explorer.exe"])
            return "Restarted Explorer."
        except Exception as exc:
            return f"Could not restart Explorer: {exc}"

    def empty_recycle_bin(self) -> str:
        try:
            os.system("rd /s /q C:\\$Recycle.Bin")
            return "Emptied the recycle bin."
        except Exception as exc:
            return f"Could not empty the recycle bin: {exc}"

    def confirm_action(self, action: str) -> str:
        return self._confirmations.get(action, f"{action.title()} requires confirmation.")
