from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from ai.gemini_client import ask_ai
from ai.memory import ConversationMemory
from ai.memory_manager import MemoryManager
from ai.memory_prompt import MemoryPromptBuilder
from commands.browser import BrowserCommands
from commands.calculator import Calculator
from commands.system import SystemCommands


class AyraAssistant:
    """Route user requests to AI or command handlers."""

    def __init__(self) -> None:
        self.memory = ConversationMemory()
        self.memory_manager = MemoryManager()
        self.memory_prompt_builder = MemoryPromptBuilder(self.memory_manager)
        self.browser = BrowserCommands()
        self.calculator = Calculator()
        self.system = SystemCommands()

    def handle(self, message: str) -> str:
        text = message.strip()
        if not text:
            return "Please say something so I can help."

        lowered = text.lower()

        if lowered.startswith("open "):
            app_name = text[5:].strip()
            return self.system.open_app(app_name)

        if "google" in lowered and "search" in lowered:
            query = re.sub(r"(google|search)\s*", "", lowered, count=1).strip()
            return self.system.search_google(query or "it")

        if "youtube" in lowered and "search" in lowered:
            query = re.sub(r"(youtube|search)\s*", "", lowered, count=1).strip()
            return self.system.search_youtube(query or "it")

        if "weather" in lowered:
            location = re.sub(r"weather", "", lowered, count=1).strip()
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

        if any(op in lowered for op in ["+", "-", "*", "/", "(", ")"]):
            return self.calculator.evaluate(text)

        if lowered.startswith("remind me"):
            reminder_text = text[len("remind me"):].strip()
            if reminder_text:
                self.memory_manager.add_reminder(reminder_text, datetime.now().isoformat(timespec="seconds"))
                return "Reminder saved."

        if lowered.startswith("take a note"):
            note_text = text[len("take a note"):].strip()
            if note_text:
                self.memory_manager.add_note("Note", note_text)
                return "Note saved."

        self._learn_from_text(text)
        prompt_context = self.memory_prompt_builder.build(text)
        try:
            response = ask_ai(text if not prompt_context else f"{prompt_context}\nUser: {text}", history=self.memory.snapshot())
        except Exception as exc:
            response = f"Sorry, I hit an issue: {exc}"

        self.memory.add_user_message(text)
        self.memory.add_assistant_message(response)
        return response

    def _learn_from_text(self, text: str) -> None:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ["my name is", "i am", "i'm", "my favorite", "i love", "i study", "my project", "i am preparing", "my profession", "my skills", "my interests"]):
            if "my name is" in lowered:
                name = text.split("my name is", 1)[1].strip().rstrip(".")
                self.memory_manager.save_user_profile(type("Profile", (), {"name": name, "nickname": None, "preferred_language": None, "theme": None, "voice_settings": None, "city": None, "country": None, "time_zone": None, "birthday": None, "profession": None, "skills": None, "interests": None})())
            elif "favorite" in lowered or "love" in lowered or "study" in lowered or "project" in lowered or "preparing" in lowered:
                self.memory_manager.save_memory(text, category="profile", importance=0.8)
