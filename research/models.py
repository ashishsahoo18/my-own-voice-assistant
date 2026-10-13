"""Data models for OLIVER 2.0 research assistant findings and citations."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ResearchSource:
    """Retrieved external information source with verified provenance."""

    title: str
    url: str
    snippet: str
    provider: str = "web"
    retrieved_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "provider": self.provider,
            "retrieved_at": self.retrieved_at,
        }


@dataclass
class ResearchFinding:
    """Individual statement supported by cited sources with confidence rating."""

    statement: str
    source_urls: list[str] = field(default_factory=list)
    is_verified: bool = True
    confidence: float = 1.0


@dataclass
class ResearchResult:
    """Complete research result separating facts, inferences, citations, and uncertainty."""

    query: str
    summary: str
    findings: list[ResearchFinding] = field(default_factory=list)
    sources: list[ResearchSource] = field(default_factory=list)
    unverified_aspects: list[str] = field(default_factory=list)
    is_offline: bool = False
    disclosure: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def format_markdown(self) -> str:
        """Format transparent structured report separating facts, citations, and uncertainty."""
        sections: list[str] = []

        # 1. Header & Summary
        title_tag = "🔬 RESEARCH REPORT (OFFLINE KNOWLEDGE)" if self.is_offline else "🔬 RESEARCH REPORT"
        sections.append(f"### {title_tag}: {self.query}\n")
        if self.summary:
            sections.append(f"**Overview:**\n{self.summary.strip()}\n")

        # 2. Key Findings with Citation Bindings
        if self.findings:
            sections.append("**Key Findings:**")
            for f in self.findings:
                verified_tag = "✓" if f.is_verified else "⚠ (Unverified)"
                source_links = ""
                if f.source_urls:
                    links = [f"[[{i+1}]]({u})" for i, u in enumerate(f.source_urls)]
                    source_links = " " + " ".join(links)
                sections.append(f"- {verified_tag} {f.statement.strip()}{source_links}")
            sections.append("")

        # 3. Unverified or Uncertain Aspects
        if self.unverified_aspects:
            sections.append("**Uncertainty & Limitations:**")
            for u in self.unverified_aspects:
                sections.append(f"- ⚠ {u.strip()}")
            sections.append("")

        # 4. Retrieved Sources List
        if self.sources:
            sections.append("**Retrieved Sources:**")
            for idx, s in enumerate(self.sources, 1):
                clean_title = s.title.strip() or "Web Source"
                sections.append(f"{idx}. [{clean_title}]({s.url}) — *{s.provider}*")
            sections.append("")
        elif self.is_offline:
            sections.append("**Retrieved Sources:**\n*None — Operating in offline mode without live web access.*\n")

        # 5. Network / Privacy Disclosure
        if self.disclosure:
            sections.append(f"> ℹ️ *{self.disclosure.strip()}*")

        return "\n".join(sections).strip()
