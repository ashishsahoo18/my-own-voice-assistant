from __future__ import annotations

import json
import urllib.request


class NewsCommands:
    """News helper using a public RSS/JSON endpoint."""

    def get_news(self, category: str = "technology") -> str:
        try:
            url = f"https://newsdata.io/api/1/news?apikey=pub_1234567890&q={category}&language=en"
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.load(response)
            articles = data.get("results", [])[:3]
            if not articles:
                return f"No news found for {category}."
            items = [f"- {article.get('title', 'Untitled')}" for article in articles]
            return "\n".join(items)
        except Exception as exc:
            return f"News lookup failed: {exc}"
