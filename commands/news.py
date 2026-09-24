from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
except ImportError:
    pass


class NewsCommands:
    """News helper using NewsData.io API."""

    def get_news(self, category: str = "technology") -> str:
        api_key = os.getenv("NEWSDATA_API_KEY", "").strip()
        if not api_key:
            return "NewsData API key is not configured. Set NEWSDATA_API_KEY in .env to enable headlines."

        try:
            url = f"https://newsdata.io/api/1/news?apikey={api_key}&q={category}&language=en"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.load(response)
            articles = data.get("results", [])[:3]
            if not articles:
                return f"No news found for {category}."
            items = [f"- {article.get('title', 'Untitled')}" for article in articles]
            return "\n".join(items)
        except Exception as exc:
            return f"News lookup failed: {exc}"

