"""Core AYRA AI assistant brain."""

from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

from ai.gemini_client import GeminiQuotaExceeded, client as gemini_client, generate_ai_response
from ai.memory import ConversationMemory
from ai.memory_manager import MemoryManager
from ai.memory_prompt import MemoryPromptBuilder
from commands.browser import BrowserCommands
from commands.calculator import Calculator
from commands.reminders import ReminderCommands
from commands.router import CommandRouter
from commands.system import SystemCommands


def google_search_answer(query: str, system: SystemCommands | None = None) -> str:
    clean_query = query.strip()
    if not clean_query:
        return "Please ask a question so I can search Google."

    search_system = system or SystemCommands()
    search_system.search_google(clean_query)
    summary = fetch_google_search_summary(clean_query)
    if summary:
        return f"{summary}\n\nSource: Google search results"
    return "I couldn't find a reliable answer for that search."


def fetch_google_search_summary(query: str) -> str:
    url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    response = requests.get(url, headers=headers, timeout=12)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    snippets: list[str] = []
    selectors = [
        'div[data-attrid="wa:/description"]',
        'div[data-attrid="kc:/knowledge_open_link"]',
        'div.BNeawe.s3v9rd.AP7Wnd',
        'div.IsZvec',
        'span.aCOpRe',
    ]

    for selector in selectors:
        for element in soup.select(selector):
            text = " ".join(element.stripped_strings)
            if len(text) >= 40 and text not in snippets:
                snippets.append(text)

    if not snippets:
        for result in soup.select("div.g"):
            snippet = result.select_one("div.IsZvec, span.aCOpRe")
            if snippet:
                text = " ".join(snippet.stripped_strings)
                if len(text) >= 40 and text not in snippets:
                    snippets.append(text)
                    if len(snippets) >= 2:
                        break

    if not snippets:
        return ""

    return " ".join(snippets[:2])


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
        self.used_google_search = False

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

        # Support compound commands like: "Create a folder named Ashish on my Desktop and create a file named Ayra.py inside it."
        if " and " in lowered and ("create folder" in lowered or "make folder" in lowered) and ("create file" in lowered or "make file" in lowered):
            # split into parts and attempt to process folder then file
            parts = [p.strip() for p in text.split(" and ", 1)]
            folder_resp = None
            file_resp = None

            # find folder part
            for part in parts:
                if any(kw in part.lower() for kw in ("create folder", "create a folder", "make folder")):
                    folder_name = self._extract_folder_name(part)
                    if folder_name:
                        folder_resp = self.system.create_folder(folder_name)
            # find file part and respect 'it' references
            for part in parts:
                if any(kw in part.lower() for kw in ("create file", "create a file", "make file")):
                    filename, folder_hint = self._extract_file_name(part)
                    if not filename:
                        continue
                    if folder_hint and folder_hint.strip() == "it":
                        if folder_name:
                            target_path = str(Path.home() / "Desktop" / folder_name / filename)
                        else:
                            target_path = str(Path.home() / "Desktop" / filename)
                    elif folder_hint:
                        if folder_hint.strip().lower() == "desktop":
                            target_path = str(Path.home() / "Desktop" / filename)
                        else:
                            target_path = str(Path.home() / "Desktop" / folder_hint.strip() / filename)
                    else:
                        target_path = str(Path.home() / "Desktop" / filename)

                    file_resp = self.system.create_file(target_path)

            results = []
            if folder_resp:
                results.append(folder_resp)
            if file_resp:
                results.append(file_resp)
            return " ".join(results) if results else None

        if "create folder" in lowered or "create a folder" in lowered or "make folder" in lowered:
            folder_name = self._extract_folder_name(text)
            if not folder_name:
                return "Please tell me the folder name. Example: create folder ashish"
            return self.system.create_folder(folder_name)

        if "create file" in lowered or "create a file" in lowered or "make file" in lowered:
            filename, folder_hint = self._extract_file_name(text)
            if not filename:
                return "Please tell me the file name. Example: create file document.txt"
            # Build target path if folder hint present
            if folder_hint:
                if folder_hint.strip().lower() == "desktop":
                    target = str(Path.home() / "Desktop" / filename)
                else:
                    target = str(Path.home() / "Desktop" / folder_hint.strip() / filename)
                return self.system.create_file(target)
            return self.system.create_file(filename)

        if self._looks_like_math(lowered):
            return self.calculator.evaluate(text)

        router_result = self.router.route(text)
        if router_result:
            return router_result

        return None

    def _extract_folder_name(self, text: str) -> str:
        """Extract folder name from natural language."""
        lowered = text.lower()

        patterns = [
            r"create a folder(?: named| name| called)?\s+(.+)",
            r"create folder(?: named| name| called)?\s+(.+)",
            r"make folder(?: named| name| called)?\s+(.+)",
            r"folder name(?: is)?\s+(.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, lowered)
            if match:
                name = match.group(1).strip()
                # remove common location qualifiers
                for suffix in (" on my desktop", " on desktop", " in my desktop", " in desktop", " on the desktop"):
                    if name.endswith(suffix):
                        name = name[: -len(suffix)].strip()
                # remove trailing punctuation
                return name.strip().strip("." )

        return ""

    def _extract_file_name(self, text: str) -> tuple[str, str | None]:
        """Extract filename and optional folder from natural language.

        Returns (filename, folder) where folder may be None or a simple name like 'Ashish' or 'Desktop'.
        """
        patterns = [
            r"(?:create|make) (?:a )?file(?: named| called)?\s+['\"]?(?P<filename>.+?)['\"]?(?:\s+(?:inside|in)\s+(?:the\s+)?(?P<folder>[^\.]+))?$",
            r"(?:create|make) (?:a )?python file(?: named| called)?\s+['\"]?(?P<filename>.+?)['\"]?(?:\s+(?:inside|in)\s+(?:the\s+)?(?P<folder>[^\.]+))?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                filename = match.group("filename").strip()
                folder = match.group("folder")
                if folder:
                    folder = folder.strip().lower()
                    for suffix in (" folder", " on my desktop", " on desktop", " in my desktop", " in desktop", " on the desktop"):
                        if folder.endswith(suffix):
                            folder = folder[: -len(suffix)].strip()
                    if folder == "it":
                        folder = "it"
                return filename, folder

        # Fallback: look for a bare filename pattern without folder context
        match = re.search(r"([\w\-. ]+\.[a-zA-Z0-9]+)", text)
        if match:
            return match.group(1).strip(), None

        return "", None

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

        if self._should_search_google(text):
            response = self._search_google_and_answer(
                text,
                note="Gemini is temporarily unavailable, so I'll search Google for the answer.",
            )
            self.used_google_search = True
            self.memory.add_user_message(text)
            self.memory.add_assistant_message(response)
            return response

        try:
            response = generate_ai_response(
                prompt,
                history=self.memory.snapshot(),
            )
            self.used_google_search = False
        except GeminiQuotaExceeded:
            response = self._search_google_and_answer(
                text,
                note="Gemini is temporarily unavailable, so I'll search Google for the answer.",
            )
            self.used_google_search = True
        except Exception:
            response = self._search_google_and_answer(
                text,
                note="I couldn't use Gemini right now, so I'm checking Google for the answer.",
            )
            self.used_google_search = True

        self.memory.add_user_message(text)
        self.memory.add_assistant_message(response)
        return response

    def _should_search_google(self, text: str) -> bool:
        """Detect if a general knowledge question should use Google search."""
        if self._is_gemini_available():
            return False

        return self._is_general_knowledge_question(text)

    def should_use_google_search(self, text: str) -> bool:
        """Tell UI whether a Google search fallback is expected."""
        return self._should_search_google(text)

    def _is_gemini_available(self) -> bool:
        return bool(getattr(gemini_client, "client", None)) and not getattr(
            gemini_client, "quota_exhausted", False
        )

    def _is_general_knowledge_question(self, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return False

        if any(lowered.startswith(prefix) for prefix in [
            "what is",
            "what are",
            "what's",
            "who is",
            "who was",
            "who created",
            "who invented",
            "who made",
            "explain",
            "how does",
            "how do",
            "how to",
            "define",
            "difference between",
            "why",
        ]):
            return True

        if lowered.endswith("?") and any(keyword in lowered for keyword in [
            "what",
            "who",
            "how",
            "why",
            "when",
            "difference",
            "define",
        ]):
            return True

        return False

    def _search_google_and_answer(self, query: str, note: str | None = None) -> str:
        clean_query = query.strip()
        if not clean_query:
            return "Please ask a question so I can search Google."

        try:
            opening_message = f"{note}\n\n" if note else ""
            # Open the browser search so the user can see Google results.
            self.system.search_google(clean_query)
            summary = self._fetch_google_search_summary(clean_query)
            if summary:
                return f"{opening_message}{summary}\n\nSource: Google search results"
            return f"{opening_message}I couldn't find a reliable answer for that search."
        except Exception as exc:
            import traceback

            print("AYRA GOOGLE SEARCH ERROR:", repr(exc))
            traceback.print_exc()
            return "Google search is currently unavailable."

    def _fetch_google_search_summary(self, query: str) -> str:
        url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        snippets: list[str] = []

        # First try the knowledge panel or featured snippet text.
        selectors = [
            'div[data-attrid="wa:/description"]',
            'div[data-attrid="kc:/knowledge_open_link"]',
            'div.BNeawe.s3v9rd.AP7Wnd',
            'div.IsZvec',
            'span.aCOpRe',
        ]

        for selector in selectors:
            for element in soup.select(selector):
                text = " ".join(element.stripped_strings)
                if len(text) >= 40 and text not in snippets:
                    snippets.append(text)

        # If no featured snippets were found, scan search result snippets.
        if not snippets:
            for result in soup.select("div.g"):
                snippet = result.select_one("div.IsZvec, span.aCOpRe")
                if snippet:
                    text = " ".join(snippet.stripped_strings)
                    if len(text) >= 40 and text not in snippets:
                        snippets.append(text)
                        if len(snippets) >= 2:
                            break

        if not snippets:
            # Try more general result snippets if featured answers are not present.
            for result in soup.select("div.g"):
                snippet = result.select_one("div.IsZvec, span.aCOpRe, div.BNeawe.s3v9rd.AP7Wnd")
                if snippet:
                    text = " ".join(snippet.stripped_strings)
                    if len(text) >= 40 and text not in snippets:
                        snippets.append(text)
                        if len(snippets) >= 2:
                            break

        if not snippets:
            return ""

        # Prefer the first two non-empty snippets for a concise answer.
        return " ".join(snippets[:2])

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