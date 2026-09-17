"""Command router for AYRA/ASHISH AI automation modules."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path

from ai.ai_service import AIService
from commands.browser import BrowserCommands
from commands.clipboard import ClipboardCommands
from commands.contacts import ContactManager
from commands.email_service import EmailService
from commands.files import FileCommands
from commands.news import NewsCommands
from commands.productivity import ProductivityCommands
from commands.screenshot import ScreenshotCommands
from commands.system import SystemCommands
from commands.weather import WeatherCommands
from commands.whatsapp import WhatsAppCommands
from commands.windows import WindowsCommands


class CommandRouter:
    """Route user intent to the correct automation module with priority ordering."""

    def __init__(self) -> None:
        self.contacts = ContactManager()
        self.browser = BrowserCommands()
        self.files = FileCommands()
        self.system = SystemCommands()
        self.clipboard = ClipboardCommands()
        self.productivity = ProductivityCommands()
        self.screenshot = ScreenshotCommands()
        self.weather = WeatherCommands()
        self.news = NewsCommands()
        self.whatsapp = WhatsAppCommands(self.contacts)
        self.email_service = EmailService(self.contacts)
        self.ai_service = AIService()
        self.windows = WindowsCommands()
        self.current_service: str | None = None
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
            # 1. WhatsApp & Email Confirmation Commands
            if "whatsapp" in lowered or (lowered.startswith("message ") and "saying" in lowered):
                res = self.whatsapp.prepare_whatsapp_command(text)
                if res:
                    return res

            if "email" in lowered or lowered.startswith("mail "):
                res = self.email_service.prepare_email_command(text)
                if res:
                    return res

            # 2. Open Commands (Websites & Apps & Folders)
            open_match = re.match(r"^(?:open|go to|launch|start|run)\s+(?:the\s+)?(.+)$", lowered)
            if open_match:
                return self._route_open(open_match.group(1))

            # 3. YouTube Direct Play vs Search
            play_match = re.match(r"^play\s+(.+)$", text, flags=re.IGNORECASE)
            if play_match:
                return self._play_youtube(play_match.group(1))

            youtube_search = re.match(
                r"^(?:search\s+youtube\s+for\s+|search\s+youtube\s+|search\s+for\s+(.+?)\s+on\s+youtube|search\s+(.+?)\s+on\s+youtube|youtube\s+search\s+)(.+)?$",
                text,
                flags=re.IGNORECASE,
            )
            if youtube_search:
                groups = [g for g in youtube_search.groups() if g is not None]
                query = groups[-1] if groups else text
                return self._search_youtube(query)

            # 4. Search Routing
            if lowered.startswith("search "):
                return self._route_search(lowered[7:].strip())

            # 5. File Commands
            file_result = self._route_file_commands(text, lowered)
            if file_result:
                return file_result

            # 6. System Commands
            system_result = self._route_system_commands(lowered)
            if system_result:
                return system_result

            # 7. Web, Weather, News
            web_result = self._route_web_commands(lowered)
            if web_result:
                return web_result

            # 8. Windows Commands
            windows_result = self._route_windows_commands(lowered)
            if windows_result:
                return windows_result

            # 9. AI Questions (what is, explain, difference between, how does, etc.)
            if self._is_ai_question(lowered):
                return self.ai_service.ask(text)

            return ""
        except Exception as exc:
            self.logger.exception("Automation error: %s", exc)
            return f"Automation error: {exc}"

    def _route_open(self, target: str) -> str:
        """Route open commands."""
        if not target:
            return "What should I open?"

        clean_target = re.sub(r"\s+(?:website|site|app|application)$", "", target).strip()
        if clean_target in self.browser.sites:
            self.current_service = clean_target
            return self.browser.open_site(clean_target)

        if clean_target in {"desktop", "documents", "downloads", "pictures", "videos"}:
            self.current_service = clean_target
            return self.files.open_folder(clean_target)

        app_res = self.windows.open_app(clean_target)
        if not app_res.startswith("I do not support"):
            self.current_service = clean_target
        return app_res

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

        if self.current_service == "youtube":
            return self._search_youtube(query)
        elif self.current_service == "github":
            return self._search_github(query)
        elif self.current_service == "stackoverflow":
            return self._search_stackoverflow(query)

        self.current_service = "google"
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

        if lowered.startswith("open "):
            target = lowered[len("open "):].strip()
            if any(keyword in target for keyword in ["folder", "desktop", "documents", "downloads", "pictures", "videos"]):
                return self.files.open_folder(target)
            return self.files.open_file(target)

        if "open the" in lowered or "open" in lowered and any(keyword in lowered for keyword in ["folder", "file"]):
            return self.files.open_folder(lowered)

        if "list files" in lowered or "list folder" in lowered or "show files" in lowered:
            path = text.split("in", 1)[-1].strip() if " in " in lowered else ""
            return self.files.list_folder(path)

        if "rename file" in lowered or "rename folder" in lowered:
            parts = lowered.replace("rename file", "").replace("rename folder", "").split(" to ")
            if len(parts) == 2:
                return self.files.rename_file(parts[0].strip(), parts[1].strip())
            return "Please provide a source and target name to rename."

        if "copy file" in lowered or "copy folder" in lowered:
            parts = lowered.replace("copy file", "").replace("copy folder", "").split(" to ")
            if len(parts) == 2:
                return self.files.copy_file(parts[0].strip(), parts[1].strip())
            return "Please provide a source and destination for copying."

        if "move file" in lowered or "move folder" in lowered:
            parts = lowered.replace("move file", "").replace("move folder", "").split(" to ")
            if len(parts) == 2:
                return self.files.move_file(parts[0].strip(), parts[1].strip())
            return "Please provide a source and destination for moving."

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

    def _is_ai_question(self, lowered: str) -> bool:
        """Determine if query is an AI Q&A question."""
        ai_triggers = [
            "what is", "what are", "explain ", "how to ", "difference between",
            "why does", "tell me about", "define ", "who is ", "where is ",
            "how does", "what does"
        ]
        return any(lowered.startswith(trig) or f" {trig}" in lowered for trig in ai_triggers) or lowered.endswith("?")

    def _search_youtube(self, query: str) -> str:
        clean_query = re.sub(r"\b(?:search|for|on|youtube)\b", "", query, flags=re.IGNORECASE).strip()
        self.current_service = "youtube"
        return self.browser.search_youtube(clean_query)

    def _play_youtube(self, query: str) -> str:
        """Find and play video on YouTube."""
        clean_query = query.strip()
        if not clean_query:
            return "What would you like me to play on YouTube?"
        self.current_service = "youtube"
        return self.browser.play_youtube(clean_query)

    def _search_github(self, query: str) -> str:
        clean_query = query.replace("github", "").strip()
        return self.browser.search_github(clean_query)

    def _search_stackoverflow(self, query: str) -> str:
        clean_query = query.replace("stack overflow", "").replace("stackoverflow", "").strip()
        return self.browser.search_stackoverflow(clean_query)

    def _search_google(self, query: str) -> str:
        clean_query = query.replace("google", "").strip()
        return self.browser.search_google(clean_query)
