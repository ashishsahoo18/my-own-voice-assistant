"""Browser automation commands for OLIVER 2.0 / AYRA AI."""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import shutil
import urllib.parse
from urllib.parse import quote_plus
import webbrowser

logger = logging.getLogger("oliver.commands.browser")


class BrowserCommands:
    """Open websites and perform web searches strictly in Mozilla Firefox."""

    PORTFOLIO_URL = "https://ashishsahoo.vercel.app/"

    def __init__(self) -> None:
        self.sites: dict[str, str] = {
            # Portfolio aliases
            "portfolio": self.PORTFOLIO_URL,
            "my portfolio": self.PORTFOLIO_URL,
            "portfolio website": self.PORTFOLIO_URL,
            "my portfolio website": self.PORTFOLIO_URL,
            "ashish portfolio": self.PORTFOLIO_URL,
            "ashish sahoo portfolio": self.PORTFOLIO_URL,

            # Popular sites & services
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "gmail": "https://mail.google.com",
            "my gmail": "https://mail.google.com",
            "drive": "https://drive.google.com",
            "google drive": "https://drive.google.com",
            "my drive": "https://drive.google.com",
            "github": "https://github.com",
            "my github": "https://github.com",
            "stackoverflow": "https://stackoverflow.com",
            "stack overflow": "https://stackoverflow.com",
            "linkedin": "https://www.linkedin.com",
            "my linkedin": "https://www.linkedin.com",
            "chatgpt": "https://chatgpt.com",
            "gemini": "https://gemini.google.com",
            "whatsapp": "https://web.whatsapp.com",
            "whatsapp web": "https://web.whatsapp.com",
            "my whatsapp": "https://web.whatsapp.com",
            "instagram": "https://www.instagram.com",
            "my instagram": "https://www.instagram.com",
            "facebook": "https://www.facebook.com",
            "x": "https://x.com",
            "my x": "https://x.com",
            "twitter": "https://x.com",
            "my twitter": "https://x.com",
            "flipkart": "https://www.flipkart.com",
            "my flipkart": "https://www.flipkart.com",
            "amazon": "https://www.amazon.in",
            "my amazon": "https://www.amazon.in",
            "wikipedia": "https://www.wikipedia.org",
            "reddit": "https://www.reddit.com",
        }

        self.site_display_names: dict[str, str] = {
            "portfolio": "Ashish Sahoo's Portfolio",
            "my portfolio": "Ashish Sahoo's Portfolio",
            "portfolio website": "Ashish Sahoo's Portfolio",
            "my portfolio website": "Ashish Sahoo's Portfolio",
            "ashish portfolio": "Ashish Sahoo's Portfolio",
            "ashish sahoo portfolio": "Ashish Sahoo's Portfolio",
            "chatgpt": "ChatGPT",
            "gemini": "Gemini",
            "gmail": "Gmail",
            "my gmail": "Gmail",
            "google": "Google",
            "youtube": "YouTube",
            "whatsapp": "WhatsApp",
            "whatsapp web": "WhatsApp Web",
            "github": "GitHub",
            "my github": "GitHub",
            "linkedin": "LinkedIn",
            "my linkedin": "LinkedIn",
            "instagram": "Instagram",
            "my instagram": "Instagram",
            "facebook": "Facebook",
            "x": "X",
            "my x": "X",
            "twitter": "Twitter",
            "my twitter": "Twitter",
            "flipkart": "Flipkart",
            "my flipkart": "Flipkart",
            "amazon": "Amazon",
            "my amazon": "Amazon",
            "wikipedia": "Wikipedia",
            "reddit": "Reddit",
        }

    def _get_firefox_controller(self):
        """Locate and return the registered Mozilla Firefox browser controller."""
        try:
            return webbrowser.get("firefox")
        except Exception:
            pass

        candidates = [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
            shutil.which("firefox"),
        ]

        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                try:
                    webbrowser.register("firefox", None, webbrowser.BackgroundBrowser(candidate))
                    return webbrowser.get("firefox")
                except Exception:
                    continue

        return None

    def _is_safe_url(self, url: str) -> tuple[bool, str]:
        """Validate URL safety using urllib.parse and ipaddress.
        
        Requires HTTP/HTTPS, valid hostname, rejects credentials, localhost, and private/restricted IPs.
        """
        clean = (url or "").strip()
        if not clean:
            return False, "Target URL cannot be empty."

        try:
            parsed = urllib.parse.urlparse(clean)
        except Exception as exc:
            return False, f"Malformed URL: {exc}"

        if parsed.scheme.lower() not in {"http", "https"}:
            return False, f"Unsupported scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "URL must contain a valid domain or hostname."

        if parsed.username or parsed.password:
            return False, "URLs with embedded credentials are prohibited for security."

        # Check for loopback / localhost
        lowered_host = hostname.lower()
        if lowered_host in {"localhost", "127.0.0.1", "::1"}:
            return False, "Access to localhost and loopback interfaces is restricted."

        # If hostname is an IP literal, validate RFC protections
        try:
            ip = ipaddress.ip_address(lowered_host)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_unspecified or ip.is_multicast:
                return False, f"Access to IP address '{ip}' is blocked by security policy."
        except ValueError:
            # Not an IP literal, domain name is valid
            pass

        return True, ""

    def open_url(self, url: str, display_name: str | None = None) -> str:
        """Open a validated URL strictly in Mozilla Firefox."""
        clean_url = (url or "").strip()
        if not clean_url:
            return "Please provide a website to open."

        if not clean_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        is_safe, reason = self._is_safe_url(clean_url)
        if not is_safe:
            return f"Security check blocked navigation: {reason}"

        name = display_name or clean_url
        ff = self._get_firefox_controller()
        # Try Firefox first if available
        if ff is not None:
            try:
                if ff.open(clean_url):
                    return f"Opening {name} in Mozilla Firefox."
            except Exception:
                # Ignore Firefox errors and fall back to default browser
                pass
        # Fallback to the system default browser (webbrowser.open)
        try:
            if webbrowser.open(clean_url):
                return f"Opening {name}."
        except Exception as exc:
            logger.error("Error opening URL %s with default browser: %s", clean_url, exc)
        return f"Failed to launch a browser for {name}."

    def open_site(self, site_name: str, url: str | None = None) -> str:
        """Open a recognized website or alias in Firefox."""
        raw_target = (site_name or url or "").strip()
        if not raw_target:
            return "Which website would you like to open?"

        clean_name = raw_target.lower().rstrip(".?! ")
        clean_name = re.sub(r"^(?:open|go to|visit|launch|show|navigate to)\s+(?:the\s+)?", "", clean_name).strip()
        clean_name = re.sub(r"\s+(?:website|site)$", "", clean_name).strip()

        # Check aliases
        if clean_name in self.sites:
            target_url = self.sites[clean_name]
            disp = self.site_display_names.get(clean_name, raw_target.title())
            return self.open_url(target_url, disp)

        # Check if the target is already a valid URL or looks like a domain name
        if clean_name.startswith(("http://", "https://")) or ("." in clean_name and " " not in clean_name):
            return self.open_url(clean_name, raw_target)

        return f"I couldn't identify the website '{raw_target}'. Which website would you like to open?"

    def search(self, query: str) -> str:
        """Search the web using Google."""
        return self.search_google(query)

    def search_google(self, query: str) -> str:
        """Search Google in Mozilla Firefox."""
        clean_query = query.strip() or "OLIVER AI"
        encoded_query = quote_plus(clean_query)
        url = f"https://www.google.com/search?q={encoded_query}"
        ff = self._get_firefox_controller()
        if ff is not None:
            try:
                ff.open(url)
                return f"Searching Google for '{clean_query}' in Mozilla Firefox."
            except Exception:
                pass
        webbrowser.open(url)
        return f"Searching Google for '{clean_query}'."

    def search_youtube(self, query: str) -> str:
        """Search YouTube."""
        from commands.youtube import YouTubeCommands
        return YouTubeCommands().search_youtube(query)

    def play_youtube(self, query: str) -> str:
        """Play video on YouTube."""
        from commands.youtube import YouTubeCommands
        return YouTubeCommands().play_youtube(query)

    def search_github(self, query: str) -> str:
        """Search GitHub in Mozilla Firefox."""
        clean_query = query.strip() or "python"
        url = f"https://github.com/search?q={quote_plus(clean_query)}"
        ff = self._get_firefox_controller()
        if ff is not None:
            try:
                ff.open(url)
                return f"Searching GitHub for '{clean_query}' in Mozilla Firefox."
            except Exception:
                pass
        webbrowser.open(url)
        return f"Searching GitHub for '{clean_query}'."

    def search_stackoverflow(self, query: str) -> str:
        """Search Stack Overflow in Mozilla Firefox."""
        clean_query = query.strip() or "python"
        url = f"https://stackoverflow.com/search?q={quote_plus(clean_query)}"
        ff = self._get_firefox_controller()
        if ff is not None:
            try:
                ff.open(url)
                return f"Searching Stack Overflow for '{clean_query}' in Mozilla Firefox."
            except Exception:
                pass
        webbrowser.open(url)
        return f"Searching Stack Overflow for '{clean_query}'."

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

    def open_portfolio(self) -> str:
        """Open Ashish Sahoo's portfolio."""
        return self.open_site("portfolio")
