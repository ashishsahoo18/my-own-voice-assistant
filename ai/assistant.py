from __future__ import annotations

import re
from typing import Optional

from ai.gemini_client import ask_ai
from ai.memory import ConversationMemory
from commands.browser import BrowserCommands
from commands.calculator import Calculator
from commands.system import SystemCommands


class AyraAssistant:
    """Route user requests to AI or command handlers."""

    def __init__(self) -> None:
        self.memory = ConversationMemory()
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

        try:
            response = ask_ai(text, history=self.memory.snapshot())
        except Exception as exc:
            response = f"Sorry, I hit an issue: {exc}"

        self.memory.add_user_message(text)
        self.memory.add_assistant_message(response)
        return response
