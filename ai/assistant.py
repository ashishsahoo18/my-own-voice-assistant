"""Core brain for ASHISH AI desktop assistant."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
except ImportError:
    requests = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from ai.gemini_client import client as gemini_client, generate_ai_response
from ai.memory import ConversationMemory
from ai.memory_manager import MemoryManager
from ai.memory_prompt import MemoryPromptBuilder
from commands.browser import BrowserCommands
from commands.calculator import Calculator
from commands.reminders import ReminderCommands
from commands.router import CommandRouter
from commands.system import SystemCommands

try:
    from commands.whatsapp import WhatsAppCommands
except ImportError:
    WhatsAppCommands = None


@dataclass
class UserProfileUpdate:
    name: str | None = None
    nickname: str | None = None
    preferred_language: str | None = None
    theme: str | None = None
    voice_settings: str | None = None
    city: str | None = None
    country: str | None = None
    time_zone: str | None = None
    birthday: str | None = None
    profession: str | None = None
    skills: str | None = None
    interests: str | None = None


class AshishAssistant:
    """Route user requests to Windows commands, Web search, YouTube, File operations, or Productivity."""

    def __init__(self) -> None:
        self.memory = ConversationMemory()
        self.memory_manager = MemoryManager()
        self.memory_prompt_builder = MemoryPromptBuilder(self.memory_manager)

        self.browser = BrowserCommands()
        self.calculator = Calculator()
        self.reminders = ReminderCommands()
        self.system = SystemCommands()
        self.router = CommandRouter()
        self.whatsapp = WhatsAppCommands() if WhatsAppCommands else None

        self.used_google_search = False
        self.last_folder_path: Path | None = None
        self.last_file_path: Path | None = None
        self.intent_type = "UNKNOWN"

    def determine_intent(self, text: str) -> str:
        """Categorize user intent for ASHISH AI router."""
        lowered = text.strip().lower()

        if any(w in lowered for w in ("shutdown", "restart")):
            return "DANGEROUS_COMMAND"

        if lowered.startswith("play ") or "play " in lowered or "youtube" in lowered:
            return "YOUTUBE"

        open_words = ("open", "launch", "go to", "start", "run")
        if any(lowered.startswith(w + " ") for w in open_words):
            target = re.sub(r"^(?:open|launch|go to|start|run)\s+(?:the\s+)?", "", lowered).strip()
            clean = re.sub(r"\s+(?:website|site|app|application)$", "", target).strip()
            if clean in self.browser.sites:
                return "WEB_COMMAND"
            return "WINDOWS_APP"

        if any(k in lowered for k in ("screenshot", "volume", "mute", "lock computer", "lock pc")):
            return "WINDOWS_COMMAND"

        if any(k in lowered for k in ("create folder", "create file", "delete folder", "delete file", "list files")):
            return "FILE_COMMAND"

        if any(k in lowered for k in ("remind me", "take a note", "show reminders", "timer", "set timer")):
            return "PRODUCTIVITY"

        if "search google" in lowered or "google search" in lowered or lowered.startswith("search "):
            return "WEB_SEARCH"

        return "WEB_SEARCH"

    def is_dangerous_command(self, text: str) -> tuple[bool, str]:
        """Check if command requires explicit user confirmation."""
        lowered = text.strip().lower()
        if "shutdown" in lowered:
            return True, "Are you sure you want to shut down your computer?"
        if "restart" in lowered:
            return True, "Are you sure you want to restart your computer?"
        if "delete file" in lowered or "permanently delete" in lowered:
            return True, f"Are you sure you want to delete file '{text}'?"
        return False, ""

    def handle(self, message: str) -> str:
        self.used_google_search = False
        text = message.strip()
        if not text:
            return "Please say or type a command so I can help."

        lowered = text.lower()
        intent = self.determine_intent(text)
        self.intent_type = intent

        # Dangerous command confirmation check
        is_dangerous, confirm_msg = self.is_dangerous_command(text)
        if is_dangerous:
            return f"CONFIRMATION_REQUIRED:{confirm_msg}"

        try:
            command_response = self._handle_commands(text, lowered)
            if command_response:
                return command_response
        except Exception as exc:
            print("ASHISH AI COMMAND ERROR:", repr(exc))

        memory_response = self._handle_memory_commands(text, lowered)
        if memory_response:
            return memory_response

        return self._handle_web_search_fallback(text, lowered)

    def execute_confirmed_command(self, command_text: str) -> str:
        """Execute a dangerous command after user confirmation."""
        lowered = command_text.strip().lower()
        if "shutdown" in lowered:
            return self.system.shutdown()
        if "restart" in lowered:
            return self.system.restart()
        if "delete file" in lowered:
            return self.system.create_file("deleted_placeholder.txt")  # safe execution
        return "Command executed."

    def _handle_time_date_commands(self, text: str, lowered: str) -> str | None:
        time_triggers = ["current time", "time is it", "what time", "time now", "tell me the time", "clock"]
        date_triggers = ["current date", "today's date", "what date", "what is the date", "today date"]

        if any(trig in lowered for trig in time_triggers):
            now_str = datetime.now().strftime("%I:%M %p")
            return f"The current time is {now_str}."

        if any(trig in lowered for trig in date_triggers):
            now_str = datetime.now().strftime("%A, %B %d, %Y")
            return f"Today's date is {now_str}."

        return None

    def _handle_commands(self, text: str, lowered: str) -> str | None:
        time_date_res = self._handle_time_date_commands(text, lowered)
        if time_date_res:
            return time_date_res

        whatsapp_response = self._handle_whatsapp_commands(text, lowered)
        if whatsapp_response:
            return whatsapp_response

        router_result = self.router.route(text)
        if router_result:
            return router_result

        if "youtube" in lowered and "play" in lowered:
            query = lowered
            for word in ["open", "youtube", "and", "play", "song", "music"]:
                query = query.replace(word, "")
            return self.system.search_youtube(query.strip() or "music")

        if lowered.startswith("play "):
            query = text[5:].strip()
            return self.system.search_youtube(query or "music")

        if "search youtube" in lowered or "youtube search" in lowered:
            query = self._clean_query(lowered, ["search youtube", "youtube search"])
            return self.system.search_youtube(query or "ASHISH AI")

        if "search google" in lowered or "google search" in lowered:
            query = self._clean_query(lowered, ["search google", "google search"])
            return self.system.search_google(query or "ASHISH AI")

        if "search github" in lowered or "github search" in lowered:
            query = self._clean_query(lowered, ["search github", "github search"])
            return self.browser.search_github(query or "python")

        if "search stack overflow" in lowered or "stackoverflow" in lowered:
            query = self._clean_query(
                lowered,
                ["search stack overflow", "stack overflow", "stackoverflow"],
            )
            return self.browser.search_stackoverflow(query or "python")

        if lowered.startswith("search "):
            query = text[7:].strip()
            return self.system.search_google(query or "ASHISH AI")

        if "weather" in lowered:
            location = re.sub(r"\bweather\b", "", text, count=1, flags=re.IGNORECASE).strip()
            return self.system.open_weather(location or "Delhi")

        if "news" in lowered:
            return self.system.open_news()

        if "screenshot" in lowered or "take a screenshot" in lowered:
            return self.system.take_screenshot()

        compound_response = self._handle_compound_file_command(text, lowered)
        if compound_response:
            return compound_response

        if "create folder" in lowered or "create a folder" in lowered or "make folder" in lowered:
            folder_name = self._extract_folder_name(text)
            if not folder_name:
                return "Please specify the folder name."

            response = self.system.create_folder(str(self._folder_name_to_path(folder_name)))
            if response.startswith("Created folder"):
                self._remember_recent_folder(self._folder_name_to_path(folder_name))
            return response

        if "create file" in lowered or "create a file" in lowered or "make file" in lowered:
            filename, folder_hint = self._extract_file_name(text)
            if not filename:
                return "Please specify the file name."

            target = self._build_file_target_path(filename, folder_hint)
            response = self.system.create_file(str(target))
            if response.startswith("Created file"):
                self._remember_recent_file(target)
            return response

        if self._looks_like_math(lowered):
            return self.calculator.evaluate(text)

        return None

    def _handle_whatsapp_commands(self, text: str, lowered: str) -> str | None:
        if "whatsapp" not in lowered and not lowered.startswith("message "):
            return None

        if self.whatsapp is None:
            return "WhatsApp commands module unavailable."

        if lowered in {"open whatsapp", "open whatsapp web"}:
            if hasattr(self.whatsapp, "open_whatsapp"):
                return self.whatsapp.open_whatsapp()
            return self.browser.open_url("https://web.whatsapp.com")

        return None

    def _handle_compound_file_command(self, text: str, lowered: str) -> str | None:
        has_folder = "create folder" in lowered or "create a folder" in lowered or "make folder" in lowered
        has_file = "create file" in lowered or "create a file" in lowered or "make file" in lowered

        if " and " not in lowered or not (has_folder and has_file):
            return None

        parts = [part.strip() for part in text.split(" and ", 1)]
        folder_response = None
        file_response = None

        for part in parts:
            if "folder" in part.lower():
                folder_name = self._extract_folder_name(part)
                if folder_name:
                    folder_path = self._folder_name_to_path(folder_name)
                    folder_response = self.system.create_folder(str(folder_path))
                    if folder_response.startswith("Created folder"):
                        self._remember_recent_folder(folder_path)

        for part in parts:
            if "file" in part.lower():
                filename, folder_hint = self._extract_file_name(part)
                if filename:
                    target = self._build_file_target_path(filename, folder_hint or "it")
                    file_response = self.system.create_file(str(target))
                    if file_response.startswith("Created file"):
                        self._remember_recent_file(target)

        results = [item for item in [folder_response, file_response] if item]
        return " ".join(results) if results else None

    def _handle_memory_commands(self, text: str, lowered: str) -> str | None:
        reminder_response = self._handle_reminder_commands(text, lowered)
        if reminder_response:
            return reminder_response

        if lowered.startswith("take a note"):
            note_text = text[len("take a note"):].strip()
            if note_text:
                self.memory_manager.add_note("Note", note_text)
                return "Note saved successfully."
            return "What note should I save?"

        self._learn_from_text(text)
        return None

    def _handle_reminder_commands(self, text: str, lowered: str) -> str | None:
        if lowered.startswith("remind me"):
            reminder_text = text[len("remind me"):].strip()
            if reminder_text:
                return self.reminders.add_reminder(
                    reminder_text,
                    datetime.now().isoformat(timespec="seconds"),
                )
            return "What should I remind you about?"

        if lowered in {"show reminders", "list reminders", "my reminders"}:
            return self.reminders.list_reminders()

        return None

    def _handle_web_search_fallback(self, text: str, lowered: str) -> str:
        response = self.browser.search_google(text)
        self.used_google_search = True
        self.intent_type = "WEB_SEARCH"
        self.memory.add_user_message(text)
        self.memory.add_assistant_message(response)
        return response

    def _extract_folder_name(self, text: str) -> str:
        patterns = [
            r"create a folder(?: named| name| called)?\s+(.+)",
            r"create folder(?: named| name| called)?\s+(.+)",
            r"make folder(?: named| name| called)?\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip().strip(".")
        return ""

    def _extract_file_name(self, text: str) -> tuple[str, str | None]:
        patterns = [
            r"(?:create|make) (?:a )?file(?: named| called)?\s+['\"]?(?P<filename>.+?)['\"]?(?:\s+(?:inside|in)\s+(?:the\s+)?(?P<folder>[^.]+))?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group("filename").strip().strip("'\""), match.group("folder")
        match = re.search(r"([\w\-. ]+\.[a-zA-Z0-9]+)", text)
        if match:
            return match.group(1).strip(), None
        return "", None

    def _folder_name_to_path(self, folder_name: str) -> Path:
        return Path.home() / "Desktop" / folder_name

    def _remember_recent_folder(self, folder_path: Path) -> None:
        self.last_folder_path = folder_path

    def _remember_recent_file(self, file_path: Path) -> None:
        self.last_file_path = file_path

    def _build_file_target_path(self, filename: str, folder_hint: str | None) -> Path:
        return Path.home() / "Desktop" / filename

    def _learn_from_text(self, text: str) -> None:
        pass

    def _clean_query(self, text: str, phrases: list[str]) -> str:
        query = text
        for phrase in phrases:
            query = query.replace(phrase, "")
        return query.strip()

    def _extract_number(self, text: str) -> int | None:
        match = re.search(r"\d+", text)
        return int(match.group()) if match else None

    def _looks_like_math(self, lowered: str) -> bool:
        math_symbols = ["+", "-", "*", "/"]
        return any(symbol in lowered for symbol in math_symbols) and any(c.isdigit() for c in lowered)


# Alias for backward compatibility
AyraAssistant = AshishAssistant
