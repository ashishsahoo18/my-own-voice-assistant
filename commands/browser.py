"""Browser automation commands for AYRA AI."""

from __future__ import annotations

import webbrowser
from urllib.parse import quote


class BrowserCommands:
    """Open websites and perform web searches."""

    def __init__(self) -> None:
        self.sites = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "gmail": "https://mail.google.com",
            "drive": "https://drive.google.com",
            "google drive": "https://drive.google.com",
            "github": "https://github.com",
            "stackoverflow": "https://stackoverflow.com",
            "stack overflow": "https://stackoverflow.com",
            "linkedin": "https://www.linkedin.com",
            "chatgpt": "https://chat.openai.com",
            "whatsapp": "https://web.whatsapp.com",
            "whatsapp web": "https://web.whatsapp.com",
            "instagram": "https://www.instagram.com",
            "facebook": "https://www.facebook.com",
            "x": "https://x.com",
            "twitter": "https://x.com",
        }

    def open_url(self, url: str, display_name: str | None = None) -> str:
        """Open a URL in the default browser."""
        clean_url = url.strip()
        if not clean_url:
            return "Please provide a website to open."

        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        webbrowser.open(clean_url)
        return f"Opened {display_name or clean_url}."

    def open_site(self, site_name: str) -> str:
        """Open a known website by name."""
        clean_name = site_name.strip().lower()
        url = self.sites.get(clean_name)

        if not url:
            return self.open_url(clean_name, site_name)

        webbrowser.open(url)
        return f"Opened {site_name}."

    def search(self, query: str) -> str:
        """Search the web using Google."""
        return self.search_google(query)

    def search_google(self, query: str) -> str:
        """Search Google."""
        clean_query = query.strip() or "AYRA AI"
        webbrowser.open(f"https://www.google.com/search?q={quote(clean_query)}")
        return f"Searching Google for {clean_query}."

    def search_youtube(self, query: str) -> str:
        """Search YouTube."""
        clean_query = query.strip() or "AYRA AI"
        webbrowser.open(f"https://www.youtube.com/results?search_query={quote(clean_query)}")
        return f"Searching YouTube for {clean_query}."

    def search_github(self, query: str) -> str:
        """Search GitHub."""
        clean_query = query.strip() or "python"
        webbrowser.open(f"https://github.com/search?q={quote(clean_query)}")
        return f"Searching GitHub for {clean_query}."

    def search_stackoverflow(self, query: str) -> str:
        """Search Stack Overflow."""
        clean_query = query.strip() or "python"
        webbrowser.open(f"https://stackoverflow.com/search?q={quote(clean_query)}")
        return f"Searching Stack Overflow for {clean_query}."

    def open_google(self) -> str:
        """Open Google."""
        return self.open_site("google")

    def open_youtube(self) -> str:
        """Open YouTube."""
        return self.open_site("youtube")

    def open_gmail(self) -> str:
        """Open Gmail."""
        return self.open_site("gmail")

    def open_linkedin(self) -> str:
        """Open LinkedIn."""
        return self.open_site("linkedin")

    def open_chatgpt(self) -> str:
        """Open ChatGPT."""
        return self.open_site("chatgpt")

    def open_drive(self) -> str:
        """Open Google Drive."""
        return self.open_site("google drive")

    def open_whatsapp(self) -> str:
        """Open WhatsApp Web."""
        return self.open_site("whatsapp web")