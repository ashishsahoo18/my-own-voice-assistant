"""YouTube automation commands for ASHISH AI."""

from __future__ import annotations

import logging
import re
import threading
import time
import urllib.parse
import webbrowser

try:
    import requests
except ImportError:
    requests = None

try:
    import pywhatkit
except Exception:
    pywhatkit = None

try:
    import pyautogui
except ImportError:
    pyautogui = None


class YouTubeCommands:
    """YouTube direct play and search automation handler."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("ashish.youtube")

    def search_youtube(self, query: str) -> str:
        """Search YouTube and open search results page without starting playback."""
        clean_query = self._clean_query(query)
        if not clean_query:
            return "What would you like to search on YouTube?"

        encoded = urllib.parse.quote_plus(clean_query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"

        try:
            opened = self._open_url(search_url)
            if not opened:
                return (
                    "YOUTUBE\n"
                    "SEARCH FAILED\n"
                    f"Reason: Could not open browser for search query '{clean_query}'."
                )
            return f"Opening YouTube results for {clean_query}."
        except Exception as exc:
            return f"YOUTUBE\nSEARCH FAILED\nReason: {exc}"

    def play_youtube(self, query: str) -> str:
        """Find the video on YouTube, open the video page, and start playback."""
        clean_query = self._clean_query(query)
        if not clean_query:
            return "What would you like me to play on YouTube?"

        video_id = self.get_video_id(clean_query)
        if not video_id:
            return (
                "YOUTUBE\n"
                "VIDEO NOT FOUND\n"
                "PLAYBACK FAILED\n"
                f"Reason: Could not resolve video ID for query '{clean_query}'."
            )

        watch_url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            opened = self._open_url(watch_url)
            if not opened and pywhatkit:
                try:
                    pywhatkit.playonyt(clean_query)
                    opened = True
                except Exception:
                    opened = False

            if not opened:
                return (
                    "YOUTUBE\n"
                    "VIDEO FOUND\n"
                    "PLAYBACK FAILED\n"
                    f"Reason: Could not launch browser for URL {watch_url}."
                )

            # Trigger keypress in background thread after video page loads
            self._schedule_playback_trigger()

            return f"Playing {clean_query}."
        except Exception as exc:
            return (
                "YOUTUBE\n"
                "VIDEO FOUND\n"
                "PLAYBACK FAILED\n"
                f"Reason: Unexpected error starting playback: {exc}"
            )

    def get_video_id(self, query: str) -> str | None:
        """Extract top video ID from YouTube search."""
        if requests:
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                }
                encoded = urllib.parse.quote(query)
                search_url = f"https://www.youtube.com/results?search_query={encoded}"
                resp = requests.get(search_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    matches = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
                    if matches:
                        return matches[0]
            except Exception as exc:
                self.logger.warning("Requests video ID resolution failed: %s", exc)

        return None

    def _open_url(self, url: str) -> bool:
        """Open URL prioritizing firefox if available, falling back to default browser."""
        try:
            try:
                browser = webbrowser.get("firefox")
                browser.open(url)
                return True
            except Exception:
                return webbrowser.open(url)
        except Exception:
            return False

    def _schedule_playback_trigger(self) -> None:
        """Send play keystroke after delay to ensure playback starts if autoplay blocked."""
        if not pyautogui:
            return

        def trigger() -> None:
            try:
                time.sleep(2.0)
                pyautogui.press("k")
            except Exception:
                pass

        threading.Thread(target=trigger, daemon=True).start()

    def _clean_query(self, query: str) -> str:
        """Remove common command prefix words."""
        cleaned = re.sub(
            r"\b(?:play|search|youtube|for|on|music|song|open|and)\b",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        return cleaned or query.strip()
