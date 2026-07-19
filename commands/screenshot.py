from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path
from typing import Optional


class ScreenshotCommands:
    """Capture screenshots and manage the screenshots folder."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.output_dir = Path(output_dir) if output_dir else project_root / "screenshots"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def take_screenshot(self, name: Optional[str] = None) -> str:
        """Capture the current screen and save it as a PNG file."""
        try:
            import pyautogui
        except ImportError:
            return "Screenshot tool is unavailable. Install pyautogui first."
        except Exception as exc:
            return f"Screenshot tool is unavailable: {exc}"

        filename = self._build_filename(name)
        output_path = self.output_dir / filename

        try:
            pyautogui.screenshot(str(output_path))
            return f"Screenshot saved to {output_path}."
        except Exception as exc:
            return f"Could not capture screenshot: {exc}"

    def open_screenshots_folder(self) -> str:
        """Open the screenshot output directory in Windows Explorer."""
        try:
            subprocess.Popen(["explorer.exe", str(self.output_dir)])
            return "Opened the screenshots folder."
        except Exception as exc:
            return f"Could not open screenshots folder: {exc}"

    def _build_filename(self, name: Optional[str]) -> str:
        """Create a safe PNG filename."""
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

        if not name or not name.strip():
            return f"ayra_screenshot_{timestamp}.png"

        safe_name = re.sub(r'[<>:"/\\|?*]+', "_", name.strip())
        safe_name = safe_name.rstrip(". ")
        if not safe_name:
            safe_name = "ayra_screenshot"

        if not safe_name.lower().endswith(".png"):
            safe_name = f"{safe_name}.png"

        return safe_name