from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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
        log_path = Path(__file__).resolve().parent.parent / "logs" / "automation.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("ayra.automation")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        return logger

    def route(self, text: str) -> str:
        lowered = text.lower().strip()
        self.logger.info("Command: %s", text)
        try:
            if lowered.startswith("open "):
                target = lowered[5:].strip()
                common_urls = {
                    "youtube": "https://www.youtube.com",
                    "google": "https://www.google.com",
                    "gmail": "https://mail.google.com",
                }
                if target in common_urls:
                    return self.browser.open_url(common_urls[target])
                if target == "whatsapp":
                    return self.whatsapp.open_whatsapp()
                if target in {"github", "linkedin", "chatgpt", "google drive"}:
                    return self._route_browser(target)
                return self.windows.open_app(target)

            if lowered.startswith("search "):
                query = lowered[7:].strip()
                if any(term in lowered for term in ["youtube", "github", "stack overflow", "google"]):
                    return self._route_browser(query)
                return self.browser.search(query)

            if lowered.startswith("create folder"):
                return self.files.create_folder(lowered.replace("create folder", "", 1).strip())
            if lowered.startswith("delete folder"):
                return self.files.delete_folder(lowered.replace("delete folder", "", 1).strip())
            if lowered.startswith("create file"):
                return self.files.create_file(lowered.replace("create file", "", 1).strip())
            if lowered.startswith("delete file"):
                return self.files.delete_file(lowered.replace("delete file", "", 1).strip())

            if "screenshot" in lowered:
                return self.screenshot.take_screenshot()

            if lowered.startswith("copy "):
                return self.clipboard.copy_text(text[len("copy "):].strip())
            if lowered.startswith("paste"):
                return self.clipboard.paste_text()

            if "weather" in lowered:
                location = lowered.replace("weather", "", 1).strip() or "Delhi"
                return self.weather.get_weather(location)
            if "news" in lowered:
                category = lowered.replace("news", "", 1).strip() or "technology"
                return self.news.get_news(category)

            if "volume" in lowered:
                if "up" in lowered:
                    return self.system.volume_up()
                if "down" in lowered:
                    return self.system.volume_down()
            if "mute" in lowered:
                return self.system.mute()
            if "shutdown" in lowered:
                return self.system.shutdown()
            if "restart" in lowered:
                return self.system.restart()
            if "sleep" in lowered:
                return self.system.sleep()

            if "whatsapp" in lowered:
                return self.whatsapp.open_whatsapp()
            if "lock" in lowered and "computer" in lowered:
                return self.windows.lock_computer()
            if "recycle" in lowered:
                return self.windows.empty_recycle_bin()
            if "explorer" in lowered:
                return self.windows.restart_explorer()
            if "downloads" in lowered or "desktop" in lowered or "documents" in lowered or "pictures" in lowered or "videos" in lowered:
                return self.files.open_folder(lowered)

            return self.browser.search(text)
        except Exception as exc:
            self.logger.error("Automation error: %s", exc)
            return f"Automation error: {exc}"

    def _route_browser(self, target: str) -> str:
        urls = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "gmail": "https://mail.google.com",
            "whatsapp": "https://web.whatsapp.com",
        }
        if target in urls and target != "whatsapp":
            return self.browser.open_url(urls[target])
        if target == "whatsapp":
            return self.whatsapp.open_whatsapp()
        mapping = {
            "youtube": self.browser.search_youtube,
            "whatsapp": self.whatsapp.open_whatsapp,
            "github": self.browser.search_github,
            "gmail": self.browser.open_gmail,
            "linkedin": self.browser.open_linkedin,
            "chatgpt": self.browser.open_chatgpt,
            "google drive": self.browser.open_drive,
        }
        handler = mapping.get(target)
        if handler is None:
            return self.browser.open_url(target)
        return handler()
