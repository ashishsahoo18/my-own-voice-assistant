"""Windows and web automation commands for AYRA AI."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import quote


class SystemCommands:
    """Perform common desktop, file, and web automation tasks."""

    def __init__(self) -> None:
        self.websites = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "gmail": "https://mail.google.com",
            "drive": "https://drive.google.com",
            "whatsapp": "https://web.whatsapp.com",
            "whatsapp web": "https://web.whatsapp.com",
            "instagram": "https://www.instagram.com",
            "facebook": "https://www.facebook.com",
            "github": "https://github.com",
            "stackoverflow": "https://stackoverflow.com",
            "stack overflow": "https://stackoverflow.com",
            "chatgpt": "https://chat.openai.com",
            "linkedin": "https://www.linkedin.com",
        }

        self.windows_apps = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "calc": "calc.exe",
            "paint": "mspaint.exe",
            "explorer": "explorer.exe",
            "file explorer": "explorer.exe",
            "command prompt": "cmd.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "settings": "ms-settings:",
            "task manager": "taskmgr.exe",
            "control panel": "control.exe",
            "vscode": "code",
            "vs code": "code",
            "visual studio code": "code",
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
        }

    def open_app(self, app_name: str) -> str:
        """Open a known website or Windows application."""
        clean_name = app_name.strip().lower()

        if not clean_name:
            return "Which app should I open?"

        if clean_name in self.websites:
            return self.open_url(self.websites[clean_name], display_name=app_name)

        if clean_name in self.windows_apps:
            target = self.windows_apps[clean_name]
            return self._launch_target(target, app_name)

        if "." in clean_name and " " not in clean_name:
            return self.open_url(f"https://{clean_name}", display_name=app_name)

        return self._launch_target(app_name, app_name)

    def open_url(self, url: str, display_name: str | None = None) -> str:
        """Open a URL in the default browser."""
        webbrowser.open(url)
        name = display_name or url
        return f"Opened {name}."

    def search_google(self, query: str) -> str:
        """Search Google in the default browser."""
        clean_query = query.strip() or "AYRA AI"
        webbrowser.open(f"https://www.google.com/search?q={quote(clean_query)}")
        return f"Searching Google for {clean_query}."

    def search_youtube(self, query: str) -> str:
        """Search YouTube in the default browser."""
        clean_query = query.strip() or "AYRA AI"
        webbrowser.open(f"https://www.youtube.com/results?search_query={quote(clean_query)}")
        return f"Searching YouTube for {clean_query}."

    def open_whatsapp(self) -> str:
        """Open WhatsApp Web."""
        return self.open_url("https://web.whatsapp.com", "WhatsApp Web")

    def open_weather(self, location: str = "Delhi") -> str:
        """Open weather results for a location."""
        clean_location = location.strip() or "Delhi"
        webbrowser.open(
            f"https://www.google.com/search?q={quote('weather ' + clean_location)}"
        )
        return f"Checking the weather for {clean_location}."

    def open_news(self) -> str:
        """Open Google News."""
        return self.open_url("https://news.google.com", "latest news")

    def take_screenshot(self, output_dir: Optional[str] = None) -> str:
        """Save a screenshot into the screenshots folder."""
        output_path = Path(output_dir or "screenshots")
        output_path.mkdir(parents=True, exist_ok=True)

        image_path = output_path / "screenshot.png"

        try:
            import pyautogui

            pyautogui.screenshot(str(image_path))
            return f"Screenshot saved to {image_path}."
        except Exception as exc:
            return f"Could not take a screenshot: {exc}"

    def create_folder(self, path: str) -> str:
        """Create a folder."""
        clean_path = path.strip()
        if not clean_path:
            return "Please provide a folder path."

        Path(clean_path).mkdir(parents=True, exist_ok=True)
        return f"Created folder at {clean_path}."

    def create_file(self, path: str) -> str:
        """Create a file."""
        clean_path = path.strip()
        if not clean_path:
            return "Please provide a file path."

        file_path = Path(clean_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch(exist_ok=True)
        return f"Created file at {clean_path}."

    def calculate(self, expression: str) -> str:
        """Evaluate a simple math expression."""
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return f"Result: {result}"
        except Exception as exc:
            return f"Calculation error: {exc}"

    def volume_up(self) -> str:
        """Increase system volume if NirCmd is installed."""
        return self._run_shell_command(
            "nircmd.exe changesysvolume 2000",
            "Volume increased.",
            "Could not increase volume",
        )

    def volume_down(self) -> str:
        """Decrease system volume if NirCmd is installed."""
        return self._run_shell_command(
            "nircmd.exe changesysvolume -2000",
            "Volume decreased.",
            "Could not decrease volume",
        )

    def mute(self) -> str:
        """Mute system volume if NirCmd is installed."""
        return self._run_shell_command(
            "nircmd.exe mutesysvolume 1",
            "Muted volume.",
            "Could not mute volume",
        )

    def brightness_up(self) -> str:
        """Placeholder for brightness support."""
        return "Brightness control is not configured yet."

    def brightness_down(self) -> str:
        """Placeholder for brightness support."""
        return "Brightness control is not configured yet."

    def sleep(self) -> str:
        """Put the computer to sleep."""
        return self._run_shell_command(
            "rundll32.exe powrprof.dll,SetSuspendState Sleep",
            "Putting the computer to sleep.",
            "Could not put the computer to sleep",
        )

    def restart(self) -> str:
        """Avoid restarting without explicit confirmation."""
        return "Restart requires confirmation."

    def shutdown(self) -> str:
        """Avoid shutting down without explicit confirmation."""
        return "Shutdown requires confirmation."

    def log_out(self) -> str:
        """Log out of Windows."""
        return self._run_shell_command(
            "shutdown /l",
            "Logging out.",
            "Could not log out",
        )

    def battery_percentage(self) -> str:
        """Return battery percentage when psutil is available."""
        try:
            import psutil

            battery = psutil.sensors_battery()
            if battery is None:
                return "Battery information is not available."

            return f"Battery is at {battery.percent:.0f}%."
        except Exception:
            return "Battery information is not available."

    def cpu_usage(self) -> str:
        """Return CPU usage when psutil is available."""
        try:
            import psutil

            return f"CPU usage is {psutil.cpu_percent(interval=0.2):.0f}%."
        except Exception:
            return "CPU usage is not available."

    def ram_usage(self) -> str:
        """Return RAM usage when psutil is available."""
        try:
            import psutil

            memory = psutil.virtual_memory()
            return f"RAM usage is {memory.percent:.0f}%."
        except Exception:
            return "RAM usage is not available."

    def disk_usage(self) -> str:
        """Return disk usage when psutil is available."""
        try:
            import psutil

            disk = psutil.disk_usage("/")
            return f"Disk usage is {disk.percent:.0f}%."
        except Exception:
            return "Disk usage is not available."

    def internet_status(self) -> str:
        """Return basic internet status."""
        try:
            import socket

            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return "Internet is connected."
        except OSError:
            return "Internet appears to be offline."

    def _launch_target(self, target: str, display_name: str) -> str:
        """Launch an executable, URI, or Windows app target."""
        try:
            if target.startswith("ms-settings:"):
                os.startfile(target)
            else:
                subprocess.Popen([target], shell=False)

            return f"Opened {display_name}."
        except Exception as exc:
            return f"Could not open {display_name}: {exc}"

    def _run_shell_command(
        self,
        command: str,
        success_message: str,
        error_prefix: str,
    ) -> str:
        """Run a trusted Windows shell command."""
        try:
            subprocess.run(command, shell=True, check=False)
            return success_message
        except Exception as exc:
            return f"{error_prefix}: {exc}"