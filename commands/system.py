import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional


class SystemCommands:
    """Perform common desktop and web automation tasks."""

    def open_app(self, app_name: str) -> str:
        try:
            subprocess.Popen([app_name])
            return f"Opened {app_name}."
        except Exception as exc:
            return f"Could not open {app_name}: {exc}"

    def search_google(self, query: str) -> str:
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return f"Searching Google for {query}."

    def search_youtube(self, query: str) -> str:
        webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
        return f"Opening YouTube for {query}."

    def open_whatsapp(self) -> str:
        webbrowser.open("https://web.whatsapp.com")
        return "Opening WhatsApp Web."

    def open_weather(self, location: str = "Delhi") -> str:
        webbrowser.open(f"https://www.google.com/search?q=weather+{location}")
        return f"Checking the weather for {location}."

    def open_news(self) -> str:
        webbrowser.open("https://news.google.com")
        return "Opening the latest news."

    def take_screenshot(self, output_dir: Optional[str] = None) -> str:
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
        Path(path).mkdir(parents=True, exist_ok=True)
        return f"Created folder at {path}."

    def create_file(self, path: str) -> str:
        Path(path).touch(exist_ok=True)
        return f"Created file at {path}."

    def calculate(self, expression: str) -> str:
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return f"Result: {result}"
        except Exception as exc:
            return f"Calculation error: {exc}"

    def volume_up(self) -> str:
        os.system("nircmd.exe changesysvolume 2000")
        return "Volume increased."

    def volume_down(self) -> str:
        os.system("nircmd.exe changesysvolume -2000")
        return "Volume decreased."

    def mute(self) -> str:
        os.system("nircmd.exe mutesysvolume 1")
        return "Muted volume."

    def brightness_up(self) -> str:
        return "Brightness control is not supported in this environment."

    def brightness_down(self) -> str:
        return "Brightness control is not supported in this environment."

    def sleep(self) -> str:
        os.system("rundll32.exe powrprof.dll,SetSuspendState Sleep")
        return "Put the computer to sleep."

    def restart(self) -> str:
        return "Restart requires confirmation."

    def shutdown(self) -> str:
        return "Shutdown requires confirmation."

    def log_out(self) -> str:
        os.system("shutdown /l")
        return "Logged out."

    def battery_percentage(self) -> str:
        return "Battery information is not available in this environment."

    def cpu_usage(self) -> str:
        return "CPU usage is not available in this environment."

    def ram_usage(self) -> str:
        return "RAM usage is not available in this environment."

    def disk_usage(self) -> str:
        return "Disk usage is not available in this environment."

    def internet_status(self) -> str:
        return "Internet status is not available in this environment."
