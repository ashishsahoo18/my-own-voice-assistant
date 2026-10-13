"""Search providers for OLIVER 2.0 research assistant with external request disclosure."""

from __future__ import annotations

import abc
import json
import logging
from typing import Any, Optional
from urllib.parse import quote, quote_plus

from core.logging import get_audit_logger
from research.models import ResearchSource
from research.security import SafeHTTPClient, SecurityError, validate_url

logger = logging.getLogger("oliver.research.providers")


class SearchProvider(abc.ABC):
    """Abstract search provider for live external information retrieval."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the information provider."""

    @abc.abstractmethod
    def search(self, query: str, max_results: int = 3) -> list[ResearchSource]:
        """Perform search query and return list of structured sources."""


class DuckDuckGoProvider(SearchProvider):
    """Retrieves factual summaries and links via DuckDuckGo public endpoints."""

    def __init__(self, http_client: Optional[SafeHTTPClient] = None) -> None:
        self.http_client = http_client or SafeHTTPClient()

    @property
    def name(self) -> str:
        return "DuckDuckGo"

    def search(self, query: str, max_results: int = 3) -> list[ResearchSource]:
        clean_query = (query or "").strip()
        if not clean_query:
            return []

        # 1. Query DuckDuckGo Instant Answer API
        endpoint = f"https://api.duckduckgo.com/?q={quote_plus(clean_query)}&format=json&no_html=1&skip_disambig=1"
        sources: list[ResearchSource] = []

        try:
            body, final_url, _ = self.http_client.get(endpoint)
            data = json.loads(body)

            abstract = data.get("AbstractText", "").strip()
            source_url = data.get("AbstractURL", "").strip()
            source_name = data.get("AbstractSource", "DuckDuckGo").strip()

            if abstract and source_url:
                sources.append(
                    ResearchSource(
                        title=f"{clean_query.title()} ({source_name})",
                        url=source_url,
                        snippet=abstract,
                        provider=self.name,
                    )
                )

            # Check Related Topics
            related = data.get("RelatedTopics", [])
            for item in related:
                if len(sources) >= max_results:
                    break
                if isinstance(item, dict):
                    text = item.get("Text", "").strip()
                    first_url = item.get("FirstURL", "").strip()
                    if text and first_url:
                        sources.append(
                            ResearchSource(
                                title=text[:60] + "...",
                                url=first_url,
                                snippet=text,
                                provider=self.name,
                            )
                        )
        except Exception as exc:
            logger.warning("DuckDuckGo search error for '%s': %s", clean_query, exc)

        return sources[:max_results]


class WikipediaProvider(SearchProvider):
    """Retrieves encyclopedic overviews via Wikimedia REST API."""

    def __init__(self, http_client: Optional[SafeHTTPClient] = None) -> None:
        self.http_client = http_client or SafeHTTPClient(connect_timeout=2.0, read_timeout=3.0)

    @property
    def name(self) -> str:
        return "Wikipedia"

    def search(self, query: str, max_results: int = 3) -> list[ResearchSource]:
        clean_query = (query or "").strip()
        if not clean_query:
            return []

        # Normalize title for REST summary endpoint
        formatted_title = quote(clean_query.replace(" ", "_"))
        endpoint = f"https://en.wikipedia.org/api/rest_v1/page/summary/{formatted_title}"
        sources: list[ResearchSource] = []

        try:
            body, final_url, _ = self.http_client.get(endpoint)
            data = json.loads(body)

            extract = data.get("extract", "").strip()
            title = data.get("title", clean_query)
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

            if extract and page_url:
                sources.append(
                    ResearchSource(
                        title=title,
                        url=page_url,
                        snippet=extract,
                        provider=self.name,
                    )
                )
        except Exception as exc:
            logger.warning("Wikipedia search error for '%s': %s", clean_query, exc)

        return sources[:max_results]


class ResearchClient:
    """Coordinates search providers, enforces privacy disclosures, and audits outbound queries."""

    def __init__(
        self,
        providers: Optional[list[SearchProvider]] = None,
        privacy_policy_allows_external: bool = True,
    ) -> None:
        self.providers = providers or [DuckDuckGoProvider(), WikipediaProvider()]
        self.privacy_policy_allows_external = privacy_policy_allows_external

    def query(self, query: str, max_results: int = 3) -> tuple[list[ResearchSource], bool, str]:
        """Query providers and aggregate sources.
        
        Returns (sources, is_offline, disclosure_message).
        """
        clean_query = query.strip()
        if not self.privacy_policy_allows_external:
            disclosure = "External network search is disabled by privacy configuration."
            logger.info(disclosure)
            return [], True, disclosure

        disclosure = f"[PRIVACY DISCLOSURE] Transmitting query '{clean_query}' to external web search providers."
        logger.warning(disclosure)

        try:
            audit = get_audit_logger()
            audit.record_event(
                event_type="RESEARCH_QUERY_DISCLOSED",
                action="research.search",
                risk_level=1,
                status="DISCLOSED",
                details={"query": clean_query, "providers": [p.name for p in self.providers]},
            )
        except Exception:
            pass

        aggregated: list[ResearchSource] = []
        for provider in self.providers:
            try:
                res = provider.search(clean_query, max_results=max_results)
                for item in res:
                    if not any(existing.url == item.url for existing in aggregated):
                        aggregated.append(item)
                    if len(aggregated) >= max_results:
                        break
            except Exception as exc:
                logger.warning("Search provider '%s' failed: %s", provider.name, exc)

            if len(aggregated) >= max_results:
                break

        is_offline = len(aggregated) == 0
        if is_offline:
            disclosure = "No live sources could be retrieved (network offline, blocked, or no matches found)."

        return aggregated[:max_results], is_offline, disclosure
