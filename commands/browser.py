from __future__ import annotations

import webbrowser
from urllib.parse import quote


class BrowserCommands:
    """Browser automation helpers for the assistant."""

    def open_url(self, url: str) -> str:
        webbrowser.open(url)
        return f"Opened {url}."

    def search(self, query: str) -> str:
        webbrowser.open(f"https://www.google.com/search?q={quote(query)}")
        return f"Searching the web for {query}."

    def search_google(self, query: str) -> str:
        webbrowser.open(f"https://www.google.com/search?q={quote(query)}")
        return f"Searching Google for {query}."

    def search_youtube(self, query: str) -> str:
        webbrowser.open(f"https://www.youtube.com/results?search_query={quote(query)}")
        return f"Opening YouTube for {query}."

    def search_github(self, query: str) -> str:
        webbrowser.open(f"https://github.com/search?q={quote(query)}")
        return f"Searching GitHub for {query}."

    def search_stackoverflow(self, query: str) -> str:
        webbrowser.open(f"https://stackoverflow.com/search?q={quote(query)}")
        return f"Searching Stack Overflow for {query}."

    def open_gmail(self) -> str:
        webbrowser.open("https://mail.google.com")
        return "Opened Gmail."

    def open_linkedin(self) -> str:
        webbrowser.open("https://www.linkedin.com")
        return "Opened LinkedIn."

    def open_chatgpt(self) -> str:
        webbrowser.open("https://chat.openai.com")
        return "Opened ChatGPT."

    def open_drive(self) -> str:
        webbrowser.open("https://drive.google.com")
        return "Opened Google Drive."
