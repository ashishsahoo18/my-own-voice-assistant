from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional


class ScreenshotCommands:
    """Capture screenshots and store them in the screenshots folder."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = Path(output_dir or Path(__file__).resolve().parent.parent / "screenshots")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def take_screenshot(self, name: Optional[str] = None) -> str:
        try:
            import pyautogui
        except Exception as exc:
            return f"Screenshot tool unavailable: {exc}"

        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = name or f"screenshot_{timestamp}.png"
        path = self.output_dir / filename
        pyautogui.screenshot(str(path))
        return f"Screenshot saved to {path}."

    def open_screenshots_folder(self) -> str:
        try:
            import subprocess
            subprocess.Popen(["explorer.exe", str(self.output_dir)])
            return f"Opened screenshots folder at {self.output_dir}."
        except Exception as exc:
            return f"Could not open screenshots folder: {exc}"
