import re
import urllib.parse
import webbrowser
import requests
try:
    import pywhatkit
except ImportError:
    pywhatkit = None
try:
    import pyautogui
except ImportError:
    pyautogui = None

class YouTubeCommands:
    """YouTube direct play and search automation."""

    def __init__(self) -> None:
        pass

    def search_youtube(self, query: str) -> str:
        """Search YouTube and open search results page."""
        clean_query = query.strip()
        if not clean_query:
            return "What would you like to search on YouTube?"
        encoded = urllib.parse.quote_plus(clean_query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        try:
            opened = webbrowser.open(url)
            if not opened:
                return f"YOUTUBE\nSEARCH FAILED\nReason: Could not open browser for search query '{clean_query}'."
            return f"Opening YouTube results for {clean_query}."
        except Exception as exc:
            return f"YOUTUBE\nSEARCH FAILED\nReason: {exc}"

    def play_youtube(self, query: str) -> str:
        """Find video on YouTube, open video page, and start playback."""
        clean_query = re.sub(r"\b(?:search|for|on|youtube|play|song|music|open|and)\b", "", query, flags=re.IGNORECASE).strip()
        if not clean_query:
            clean_query = query.strip()
        if not clean_query:
            return "What would you like me to play on YouTube?"

        video_id = self._fetch_video_id(clean_query)
        if not video_id:
            return f"YOUTUBE\nVIDEO NOT FOUND\nPLAYBACK FAILED\nReason: Could not find matching video for '{clean_query}'."

        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        
        try:
            opened = webbrowser.open(watch_url)
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

            # Optional desktop interaction to trigger autoplay / resume if paused
            if pyautogui:
                try:
                    # Give browser a moment to load then send key 'k' to toggle play
                    import time
                    time.sleep(1.5)
                    pyautogui.press("k")
                except Exception:
                    pass

            return f"Playing {clean_query}."
        except Exception as exc:
            return (
                "YOUTUBE\n"
                "VIDEO FOUND\n"
                "PLAYBACK FAILED\n"
                f"Reason: Unexpected error while opening video: {exc}"
            )

    def _fetch_video_id(self, query: str) -> str | None:
        """Fetch video ID for query using requests or pywhatkit."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        encoded = urllib.parse.quote(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"

        try:
            resp = requests.get(search_url, headers=headers, timeout=5)
            if resp.status_code == 200:
                matches = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", resp.text)
                if matches:
                    return matches[0]
        except Exception:
            pass

        if pywhatkit:
            try:
                # pywhatkit.playonyt fetches video URL internally
                # We can extract video ID from pywhatkit's logic if needed or fallback
                pass
            except Exception:
                pass

        return None

if __name__ == "__main__":
    yt = YouTubeCommands()
    print("Testing Play Ik Mulaqaat:")
    print(yt.play_youtube("Ik Mulaqaat"))
    print("\nTesting Search Python Tutorials:")
    print(yt.search_youtube("Python Tutorials"))
