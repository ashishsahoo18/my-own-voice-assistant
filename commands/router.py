"""Command router for AYRA AI automation modules."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from commands.browser import BrowserCommands
from commands.clipboard import ClipboardCommands
from commands.files import FileCommands
from commands.news import NewsCommands
from commands.productivity import ProductivityCommands
from commands.screenshot import ScreenshotCommands
from commands.system import SystemCommands
from commands.weather import WeatherCommands
from commands.whatsapp import WhatsAppCommands
from commands.windows import WindowsCommands


class CommandRouter:
    """Route user intent to the correct automation module."""

    def __init__(self) -> None:
        self.browser = BrowserCommands()
        self.files = FileCommands()
        self.system = SystemCommands()
        self.clipboard = ClipboardCommands()
        self.productivity = ProductivityCommands()
        self.screenshot = ScreenshotCommands()
        self.weather = WeatherCommands()
        self.news = NewsCommands()
        self.whatsapp = WhatsAppCommands()
        self.windows = WindowsCommands()
        self.logger = self._create_logger()

    def _create_logger(self) -> logging.Logger:
        """Create or reuse automation logger."""
        log_path = Path(__file__).resolve().parent.parent / "logs" / "automation.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("ayra.automation")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if not logger.handlers:
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)

        return logger

    def route(self, text: str) -> str:
        """Route text to automation command handlers.

        Returns an empty string when no automation intent is found.
        """
        lowered = text.lower().strip()

        if not lowered:
            return ""

        self.logger.info("Command: %s", text)

        try:
            if lowered.startswith("open "):
                return self._route_open(lowered[5:].strip())

            if lowered.startswith("search "):
                return self._route_search(lowered[7:].strip())

            file_result = self._route_file_commands(text, lowered)
            if file_result:
                return file_result

            system_result = self._route_system_commands(lowered)
            if system_result:
                return system_result

            web_result = self._route_web_commands(lowered)
            if web_result:
                return web_result

            windows_result = self._route_windows_commands(lowered)
            if windows_result:
                return windows_result

            return ""
        except Exception as exc:
            self.logger.exception("Automation error: %s", exc)
            return f"Automation error: {exc}"

    def _route_open(self, target: str) -> str:
        """Route open commands."""
        if not target:
            return "What should I open?"

        websites = {
            "youtube": self.browser.open_youtube,
            "google": self.browser.open_google,
            "gmail": self.browser.open_gmail,
            "github": lambda: self.browser.open_site("github"),
            "linkedin": self.browser.open_linkedin,
            "chatgpt": self.browser.open_chatgpt,
            "google drive": self.browser.open_drive,
            "drive": self.browser.open_drive,
            "whatsapp": self.whatsapp.open_whatsapp,
            "whatsapp web": self.whatsapp.open_whatsapp,
        }

        handler = websites.get(target)
        if handler:
            return handler()

        return self.windows.open_app(target)

    def _route_search(self, query: str) -> str:
        """Route search commands."""
        if not query:
            return "What should I search?"

        search_routes: list[tuple[tuple[str, ...], Callable[[str], str]]] = [
            (("youtube",), self._search_youtube),
            (("github",), self._search_github),
            (("stack overflow", "stackoverflow"), self._search_stackoverflow),
            (("google",), self._search_google),
        ]

        for keywords, handler in search_routes:
            if any(keyword in query for keyword in keywords):
                return handler(query)

        return self.browser.search(query)

    def _route_file_commands(self, text: str, lowered: str) -> str:
        """Route file and folder commands."""
        file_commands = {
            "create folder": self.files.create_folder,
            "delete folder": self.files.delete_folder,
            "create file": self.files.create_file,
            "delete file": self.files.delete_file,
        }

        for prefix, handler in file_commands.items():
            if lowered.startswith(prefix):
                path = text[len(prefix):].strip()
                return handler(path)

        folder_keywords = ["downloads", "desktop", "documents", "pictures", "videos"]
        if any(keyword in lowered for keyword in folder_keywords):
            return self.files.open_folder(lowered)

        return ""

    def _route_system_commands(self, lowered: str) -> str:
        """Route system commands."""
        if "screenshot" in lowered:
            return self.screenshot.take_screenshot()

        if lowered.startswith("copy "):
            return self.clipboard.copy_text(lowered[len("copy "):].strip())

        if lowered.startswith("paste"):
            return self.clipboard.paste_text()

        if "volume" in lowered:
            if "up" in lowered or "increase" in lowered:
                return self.system.volume_up()
            if "down" in lowered or "decrease" in lowered:
                return self.system.volume_down()

        if "mute" in lowered:
            return self.system.mute()

        if "shutdown" in lowered:
            return self.system.shutdown()

        if "restart" in lowered:
            return self.system.restart()

        if "sleep" in lowered:
            return self.system.sleep()

        return ""

    def _route_web_commands(self, lowered: str) -> str:
        """Route weather, news, and WhatsApp commands."""
        if "weather" in lowered:
            location = lowered.replace("weather", "", 1).strip() or "Delhi"
            return self.weather.get_weather(location)

        if "news" in lowered:
            category = lowered.replace("news", "", 1).strip() or "technology"
            return self.news.get_news(category)

        if "whatsapp" in lowered:
            return self.whatsapp.open_whatsapp()

        return ""

    def _route_windows_commands(self, lowered: str) -> str:
        """Route Windows-specific automation commands."""
        if "lock" in lowered and "computer" in lowered:
            return self.windows.lock_computer()

        if "recycle" in lowered:
            return self.windows.empty_recycle_bin()

        if "restart explorer" in lowered:
            return self.windows.restart_explorer()

        return ""

    def _search_youtube(self, query: str) -> str:
        clean_query = query.replace("youtube", "").strip()
        return self.browser.search_youtube(clean_query)

    def _search_github(self, query: str) -> str:
        clean_query = query.replace("github", "").strip()
        return self.browser.search_github(clean_query)

    def _search_stackoverflow(self, query: str) -> str:
        clean_query = query.replace("stack overflow", "").replace("stackoverflow", "").strip()
        return self.browser.search_stackoverflow(clean_query)

    def _search_google(self, query: str) -> str:
        clean_query = query.replace("google", "").strip()
        return self.browser.search_google(clean_query)