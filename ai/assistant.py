"""Core AYRA AI assistant brain."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

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


def google_search_answer(query: str) -> str:
    """Search Google and return a short readable answer."""
    clean_query = query.strip()
    if not clean_query:
        return "Please ask a question so I can search Google."

    summary = fetch_google_search_summary(clean_query)
    if summary:
        return f"{summary}\n\nSource: Google search results"

    return "I could not find a reliable answer for that search."


def fetch_google_search_summary(query: str) -> str:
    """Fetch a short summary from Google search result snippets."""
    url = f"https://www.google.com/search?hl=en&gl=us&pws=0&q={quote_plus(query)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=12)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    snippets: list[str] = []

    selectors = [
        'div[data-attrid^="wa:"]',
        'div[data-attrid^="kc:"]',
        'div[class*="BNeawe"]',
        'div[class*="IsZvec"]',
        'span[class*="aCOpRe"]',
        'div[jsname="LwH6nd"]',
        'div[jsname="r5hl4d"]',
    ]

    for selector in selectors:
        for element in soup.select(selector):
            text = " ".join(element.stripped_strings)
            if len(text) >= 40 and text not in snippets:
                snippets.append(text)

    if not snippets:
        for result in soup.select("div.g"):
            text = " ".join(result.stripped_strings)
            if 80 <= len(text) <= 600 and text not in snippets:
                snippets.append(text)
                if len(snippets) >= 2:
                    break

    return " ".join(snippets[:2]) if snippets else ""


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
    """Route user requests to commands, memory, search, or AI."""

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
        self.intent_type = "unknown"

    def handle(self, message: str) -> str:
        """Handle a user message and return AYRA's response."""
        self.used_google_search = False
        self.intent_type = "unknown"

        text = message.strip()
        if not text:
            return "Please say something so I can help."

        lowered = text.lower()

        command_response = self._handle_commands(text, lowered)
        if command_response:
            self.intent_type = "local_action"
            return command_response

        memory_response = self._handle_memory_commands(text, lowered)
        if memory_response:
            self.intent_type = "memory_action"
            return memory_response

        return self._handle_ai_chat(text, lowered)

    def _handle_commands(self, text: str, lowered: str) -> str | None:
        """Handle desktop, browser, file, folder, WhatsApp, and calculator commands."""
        whatsapp_response = self._handle_whatsapp_commands(text, lowered)
        if whatsapp_response:
            return whatsapp_response

        if "youtube" in lowered and "play" in lowered:
            query = lowered
            for word in ["open", "youtube", "and", "play", "song", "music"]:
                query = query.replace(word, "")
            return self.system.search_youtube(query.strip() or "music")

        if lowered.startswith("play "):
            query = text[5:].strip()
            return self.system.search_youtube(query or "music")

        if self._is_youtube_open_command(lowered):
            return self.browser.open_url("https://www.youtube.com")

        if self._is_google_open_command(lowered):
            return self.browser.open_url("https://www.google.com")

        if lowered.startswith("open "):
            app_name = text[5:].strip()
            return self.system.open_app(app_name)

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

        compound_response = self._handle_compound_file_command(text, lowered)
        if compound_response:
            return compound_response

        if "create folder" in lowered or "create a folder" in lowered or "make folder" in lowered:
            folder_name = self._extract_folder_name(text)
            if not folder_name:
                return "Please tell me the folder name. Example: create folder ashish"

            response = self.system.create_folder(folder_name)
            if response.startswith("Created folder"):
                self._remember_recent_folder(self._folder_name_to_path(folder_name))
            return response

        if "create file" in lowered or "create a file" in lowered or "make file" in lowered:
            filename, folder_hint = self._extract_file_name(text)
            if not filename:
                return "Please tell me the file name. Example: create file document.txt"

            target = self._build_file_target_path(filename, folder_hint)
            response = self.system.create_file(str(target))
            if response.startswith("Created file"):
                self._remember_recent_file(target)
            return response

        if self._looks_like_math(lowered):
            return self.calculator.evaluate(text)

        router_result = self.router.route(text)
        if router_result:
            return router_result

        return None

    def _handle_whatsapp_commands(self, text: str, lowered: str) -> str | None:
        """Handle WhatsApp commands if WhatsAppCommands is available."""
        if "whatsapp" not in lowered:
            return None

        if self.whatsapp is None:
            return "WhatsApp commands are not installed. Add commands/whatsapp.py first."

        if lowered in {"open whatsapp", "open whatsapp web"}:
            return self.whatsapp.open_whatsapp()

        if lowered.startswith("send whatsapp to "):
            parts = text[len("send whatsapp to "):].split(" message ", 1)
            if len(parts) != 2:
                return "Use: send whatsapp to contact_name message your message"
            contact_name, message = parts
            return self.whatsapp.send_to_contact(contact_name, message)

        if lowered.startswith("send whatsapp number "):
            parts = text[len("send whatsapp number "):].split(" message ", 1)
            if len(parts) != 2:
                return "Use: send whatsapp number 919876543210 message your message"
            number, message = parts
            return self.whatsapp.send_message(number, message)

        return None

    def _handle_compound_file_command(self, text: str, lowered: str) -> str | None:
        """Handle commands that create a folder and file together."""
        has_folder = "create folder" in lowered or "create a folder" in lowered or "make folder" in lowered
        has_file = "create file" in lowered or "create a file" in lowered or "make file" in lowered

        if " and " not in lowered or not (has_folder and has_file):
            return None

        parts = [part.strip() for part in text.split(" and ", 1)]
        folder_response = None
        file_response = None
        folder_name = None

        for part in parts:
            part_lowered = part.lower()
            if "folder" in part_lowered:
                folder_name = self._extract_folder_name(part)
                if folder_name:
                    folder_response = self.system.create_folder(folder_name)
                    if folder_response.startswith("Created folder"):
                        self._remember_recent_folder(self._folder_name_to_path(folder_name))

        for part in parts:
            part_lowered = part.lower()
            if "file" in part_lowered:
                filename, folder_hint = self._extract_file_name(part)
                if filename:
                    target = self._build_file_target_path(filename, folder_hint or "it")
                    file_response = self.system.create_file(str(target))
                    if file_response.startswith("Created file"):
                        self._remember_recent_file(target)

        results = [item for item in [folder_response, file_response] if item]
        return " ".join(results) if results else None

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

    def _handle_ai_chat(self, text: str, lowered: str) -> str:
        """Route conversation and knowledge questions through AI or search."""
        prompt_context = self.memory_prompt_builder.build(text)
        prompt = text if not prompt_context else f"{prompt_context}\nUser: {text}"

        if self._should_search_google(text, lowered):
            response = self._search_google_and_answer(text)
            if not response or "couldn't search" in response.lower():
                response = generate_ai_response(prompt, history=self.memory.snapshot())
            self.used_google_search = True
            self.intent_type = "web_search"
        else:
            response = generate_ai_response(prompt, history=self.memory.snapshot())
            self.used_google_search = False
            self.intent_type = "conversation"

        self.memory.add_user_message(text)
        self.memory.add_assistant_message(response)
        return response

    def _should_search_google(self, text: str, lowered: str) -> bool:
        """Use Google only for current or explicitly verified information."""
        if self._is_explicit_search_command(lowered):
            return False

        if self._is_current_info_question(lowered):
            return True

        verify_words = ["verify", "check online", "search and tell", "latest", "current"]
        return any(word in lowered for word in verify_words)

    def should_use_google_search(self, text: str) -> bool:
        """Tell UI whether a background Google answer is expected."""
        lowered = text.strip().lower()
        if not lowered:
            return False
        return self._should_search_google(text, lowered)

    def _is_gemini_available(self) -> bool:
        """Return True when Gemini is configured and quota is not exhausted."""
        return bool(getattr(gemini_client, "client", None)) and not getattr(
            gemini_client,
            "quota_exhausted",
            False,
        )

    def _search_google_and_answer(self, query: str) -> str:
        """Search Google in the background and return a readable answer."""
        clean_query = query.strip()
        if not clean_query:
            return "Please ask a question so I can search Google."

        try:
            summary = fetch_google_search_summary(clean_query)
            if summary:
                return f"{summary}\n\nSource: Google search results"
            return "I could not find a reliable answer for that search."
        except Exception:
            return "I could not search Google right now."

    def _extract_folder_name(self, text: str) -> str:
        """Extract folder name from natural language."""
        patterns = [
            r"create a folder(?: named| name| called)?\s+(.+)",
            r"create folder(?: named| name| called)?\s+(.+)",
            r"make folder(?: named| name| called)?\s+(.+)",
            r"folder name(?: is)?\s+(.+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                name = re.sub(r"\s+on\s+(my\s+)?desktop$", "", name, flags=re.IGNORECASE)
                name = re.sub(r"\s+in\s+(my\s+)?desktop$", "", name, flags=re.IGNORECASE)
                return name.strip().strip(".")

        return ""

    def _extract_file_name(self, text: str) -> tuple[str, str | None]:
        """Extract filename and optional folder hint."""
        patterns = [
            r"(?:create|make) (?:a )?python file(?: named| called)?\s+['\"]?(?P<filename>.+?)['\"]?(?:\s+(?:inside|in)\s+(?:the\s+)?(?P<folder>[^.]+))?$",
            r"(?:create|make) (?:a )?file(?: named| called)?\s+['\"]?(?P<filename>.+?)['\"]?(?:\s+(?:inside|in)\s+(?:the\s+)?(?P<folder>[^.]+))?$",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                filename = match.group("filename").strip().strip("'\"")
                folder = match.group("folder")

                if folder:
                    folder = folder.strip()
                    folder = re.sub(r"\s+folder$", "", folder, flags=re.IGNORECASE)
                    folder = re.sub(r"\s+on\s+(my\s+)?desktop$", "", folder, flags=re.IGNORECASE)

                return filename, folder

        match = re.search(r"([\w\-. ]+\.[a-zA-Z0-9]+)", text)
        if match:
            return match.group(1).strip(), None

        return "", None

    def _folder_name_to_path(self, folder_name: str) -> Path:
        """Convert folder name to a useful path."""
        if any(separator in folder_name for separator in ("/", "\\", ":")):
            return Path(folder_name)
        return Path.home() / "Desktop" / folder_name

    def _remember_recent_folder(self, folder_path: Path) -> None:
        """Keep short-term folder context for follow-up commands."""
        self.last_folder_path = folder_path

    def _remember_recent_file(self, file_path: Path) -> None:
        """Keep short-term file context for follow-up commands."""
        self.last_file_path = file_path

    def _build_file_target_path(self, filename: str, folder_hint: str | None) -> Path:
        """Build the full target path for a new file."""
        if folder_hint:
            folder_path = self._resolve_folder_hint(folder_hint)
        else:
            folder_path = self.last_folder_path or Path.home() / "Desktop"

        return (folder_path or Path.home() / "Desktop") / filename

    def _resolve_folder_hint(self, folder_hint: str) -> Path | None:
        """Resolve words like 'it', 'desktop', or folder names into a path."""
        hint = folder_hint.strip().lower()
        if hint in {"it", "that", "there"} and self.last_folder_path:
            return self.last_folder_path

        if hint in {"desktop", "my desktop", "the desktop"}:
            return Path.home() / "Desktop"

        files_tool = getattr(self.router, "files", None)
        known_folders = getattr(files_tool, "known_folders", {})
        if hint in known_folders:
            return known_folders[hint]

        if any(separator in folder_hint for separator in ("/", "\\", ":")):
            return Path(folder_hint)

        return Path.home() / "Desktop" / folder_hint

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

    def _is_current_info_question(self, lowered: str) -> bool:
        """Return True for questions that need current information."""
        current_markers = [
            "today",
            "current",
            "latest",
            "recent",
            "now",
            "weather",
            "news",
            "update",
            "score",
            "price",
            "version",
            "stock",
        ]
        return any(marker in lowered for marker in current_markers)

    def _is_explicit_search_command(self, lowered: str) -> bool:
        """Return True when the user explicitly asks to open a search page."""
        search_triggers = [
            "search google",
            "google search",
            "search youtube",
            "youtube search",
            "search github",
            "github search",
            "search stack overflow",
            "stackoverflow",
            "search ",
        ]
        return any(trigger in lowered for trigger in search_triggers)

    def _clean_query(self, text: str, phrases: list[str]) -> str:
        """Remove command phrases and return the search query."""
        query = text
        for phrase in phrases:
            query = query.replace(phrase, "")
        return query.strip()

    def _extract_number(self, text: str) -> int | None:
        """Extract the first integer from text."""
        match = re.search(r"\d+", text)
        return int(match.group()) if match else None

    def _looks_like_math(self, lowered: str) -> bool:
        """Detect simple math expressions."""
        math_symbols = ["+", "-", "*", "/", "(", ")"]
        has_symbol = any(symbol in lowered for symbol in math_symbols)
        has_number = any(char.isdigit() for char in lowered)
        return has_symbol and has_number