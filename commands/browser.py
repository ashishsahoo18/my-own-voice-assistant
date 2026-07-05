import webbrowser


class BrowserCommands:
    """Simple browser actions for the assistant."""

    def open_url(self, url: str) -> str:
        webbrowser.open(url)
        return f"Opened {url}."

    def search(self, query: str) -> str:
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return f"Searching the web for {query}."
