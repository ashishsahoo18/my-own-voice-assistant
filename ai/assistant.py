"""Core AYRA AI assistant brain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ai.gemini_client import generate_ai_response
from ai.memory import ConversationMemory
from ai.memory_manager import MemoryManager
from ai.memory_prompt import MemoryPromptBuilder
from commands.browser import BrowserCommands
from commands.calculator import Calculator
from commands.reminders import ReminderCommands
from commands.router import CommandRouter
from commands.system import SystemCommands


@dataclass
class UserProfileUpdate:
    """Small profile object compatible with MemoryManager."""

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


class AyraAssistant:
    """Route user requests to commands, memory, reminders, or Gemini AI."""

    def __init__(self) -> None:
        self.memory = ConversationMemory()
        self.memory_manager = MemoryManager()
        self.memory_prompt_builder = MemoryPromptBuilder(self.memory_manager)

        self.browser = BrowserCommands()
        self.calculator = Calculator()
        self.reminders = ReminderCommands()
        self.system = SystemCommands()
        self.router = CommandRouter()

    def handle(self, message: str) -> str:
        """Handle a user message and return AYRA's response."""
        text = message.strip()
        if not text:
            return "Please say something so I can help."

        lowered = text.lower()

        command_response = self._handle_commands(text, lowered)
        if command_response:
            return command_response

        memory_response = self._handle_memory_commands(text, lowered)
        if memory_response:
            return memory_response

        return self._handle_ai_chat(text)

    def _handle_commands(self, text: str, lowered: str) -> str | None:
        """Handle deterministic desktop, browser, weather, and calculator commands."""
        if lowered.startswith("open "):
            app_name = text[5:].strip()
            return self.system.open_app(app_name)

        if self._is_youtube_open_command(lowered):
            return self.browser.open_url("https://www.youtube.com")

        if self._is_google_open_command(lowered):
            return self.browser.open_url("https://www.google.com")

        if "search youtube" in lowered or "youtube search" in lowered:
            query = self._clean_query(lowered, ["search youtube", "youtube search"])
            return self.system.search_youtube(query or "AYRA AI")

        if "search google" in lowered or "google search" in lowered:
            query = self._clean_query(lowered, ["search google", "google search"])
            return self.system.search_google(query or "AYRA AI")

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
            return self.system.search_google(query or "AYRA AI")

        if "weather" in lowered:
            location = re.sub(r"\bweather\b", "", text, count=1, flags=re.IGNORECASE).strip()
            return self.system.open_weather(location or "Delhi")

        if "news" in lowered:
            return self.system.open_news()

        if "screenshot" in lowered:
            return self.system.take_screenshot()

        if "create folder" in lowered:
            path = text.split("create folder", 1)[1].strip()
            return self.system.create_folder(path)

        if "create file" in lowered:
            path = text.split("create file", 1)[1].strip()
            return self.system.create_file(path)

        if self._looks_like_math(lowered):
            return self.calculator.evaluate(text)

        router_result = self.router.route(text)
        if router_result:
            return router_result

        return None

    def _handle_memory_commands(self, text: str, lowered: str) -> str | None:
        """Handle notes, reminders, and profile learning commands."""
        reminder_response = self._handle_reminder_commands(text, lowered)
        if reminder_response:
            return reminder_response

        if lowered.startswith("take a note"):
            note_text = text[len("take a note"):].strip()
            if note_text:
                self.memory_manager.add_note("Note", note_text)
                return "Note saved."
            return "What note should I save?"

        self._learn_from_text(text)
        return None

    def _handle_reminder_commands(self, text: str, lowered: str) -> str | None:
        """Handle reminder commands."""
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

        if lowered.startswith("complete reminder"):
            reminder_id = self._extract_number(lowered)
            if reminder_id is None:
                return "Please tell me the reminder number to complete."
            return self.reminders.complete_reminder(reminder_id)

        if lowered.startswith("delete reminder"):
            reminder_id = self._extract_number(lowered)
            if reminder_id is None:
                return "Please tell me the reminder number to delete."
            return self.reminders.delete_reminder(reminder_id)

        return None

    def _handle_ai_chat(self, text: str) -> str:
        """Send normal conversation to Gemini with memory context."""
        prompt_context = self.memory_prompt_builder.build(text)
        prompt = text if not prompt_context else f"{prompt_context}\nUser: {text}"

        try:
            response = generate_ai_response(
                prompt,
                history=self.memory.snapshot(),
            )
        except Exception:
            response = "I am sorry, I could not process that request right now."

        self.memory.add_user_message(text)
        self.memory.add_assistant_message(response)
        return response

    def _learn_from_text(self, text: str) -> None:
        """Store useful long-term user facts."""
        lowered = text.lower()
        profile_keywords = [
            "my name is",
            "i am",
            "i'm",
            "my favorite",
            "i love",
            "i study",
            "my project",
            "i am preparing",
            "my profession",
            "my skills",
            "my interests",
        ]

        if not any(keyword in lowered for keyword in profile_keywords):
            return

        if "my name is" in lowered:
            name = text.split("my name is", 1)[1].strip().rstrip(".")
            self.memory_manager.save_user_profile(UserProfileUpdate(name=name))
            return

        self.memory_manager.save_memory(text, category="profile", importance=0.8)

    def _is_youtube_open_command(self, lowered: str) -> bool:
        """Return True when the user wants to open YouTube directly."""
        open_words = ["open", "launch", "start", "go to"]
        return "youtube" in lowered and any(word in lowered for word in open_words)

    def _is_google_open_command(self, lowered: str) -> bool:
        """Return True when the user wants to open Google directly."""
        open_words = ["open", "launch", "start", "go to"]
        return "google" in lowered and any(word in lowered for word in open_words)

    def _clean_query(self, text: str, phrases: list[str]) -> str:
        """Remove command phrases and return the search query."""
        query = text
        for phrase in phrases:
            query = query.replace(phrase, "")
        return query.strip()

    def _extract_number(self, text: str) -> int | None:
        """Extract the first integer from text."""
        match = re.search(r"\d+", text)
        if not match:
            return None
        return int(match.group())

    def _looks_like_math(self, lowered: str) -> bool:
        """Detect simple math expressions."""
        math_symbols = ["+", "-", "*", "/", "(", ")"]
        has_symbol = any(symbol in lowered for symbol in math_symbols)
        has_number = any(char.isdigit() for char in lowered)
        return has_symbol and has_number