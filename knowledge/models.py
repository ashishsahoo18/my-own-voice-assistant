"""Data models for OLIVER 2.0 Documents & Knowledge Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DocumentPage:
    """Single page or section of an extracted document."""

    page_number: int
    text: str


@dataclass
class DocumentMetadata:
    """Metadata describing an indexed document."""

    doc_id: str
    filename: str
    file_path: str
    file_type: str
    file_size: int
    file_hash: str
    total_chunks: int = 0
    total_pages: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class DocumentChunk:
    """Bounded passage chunk with source metadata."""

    chunk_id: str
    doc_id: str
    chunk_index: int
    page_number: int
    content: str
    char_count: int
    filename: str = ""
    created_at: str = ""


@dataclass
class DocumentReadResult:
    """Result of extracting text and structure from a document file."""

    file_path: str
    filename: str
    file_type: str
    pages: list[DocumentPage]
    full_text: str
    total_pages: int
    file_size: int
    file_hash: str
    is_success: bool = True
    error: Optional[str] = None


@dataclass
class DocumentChunkMatch:
    """Match result from FTS5 passage search with BM25 score."""

    chunk: DocumentChunk
    rank_score: float = 0.0
    snippet: str = ""


@dataclass
class DocumentSearchResult:
    """Search results across indexed documents."""

    query: str
    matches: list[DocumentChunkMatch] = field(default_factory=list)
    total_matches: int = 0
    is_offline: bool = False

    def format_markdown(self) -> str:
        md = [f"### 📚 Knowledge Search Results for '{self.query}'", ""]
        if not self.matches:
            md.append("No matching passages found in indexed documents.\n")
            return "\n".join(md)

        md.append(f"Found {len(self.matches)} relevant passage(s):\n")
        for i, match in enumerate(self.matches, 1):
            c = match.chunk
            page_info = f" (Page {c.page_number})" if c.page_number > 0 else ""
            md.append(f"**{i}. `{c.filename}`{page_info}** [Score: {match.rank_score:.2f}]:")
            snippet_text = match.snippet or c.content[:300]
            md.append(f"> {snippet_text}\n")

        return "\n".join(md)


@dataclass
class DocumentSummaryResult:
    """Synthesized summary of an indexed document."""

    doc_id: str
    filename: str
    summary: str
    key_points: list[str] = field(default_factory=list)
    total_pages: int = 1
    total_chunks: int = 0
    is_offline: bool = False
    disclaimer: str = "Extracted from indexed document passages."

    def format_markdown(self) -> str:
        page_str = f" • {self.total_pages} page(s)" if self.total_pages > 1 else ""
        md = [f"### 📄 Document Summary: `{self.filename}`{page_str}", ""]
        md.append(f"**Overview:**\n{self.summary}\n")

        if self.key_points:
            md.append("**Key Findings & Points:**")
            for pt in self.key_points:
                md.append(f"- {pt}")
            md.append("")

        md.append(f"> ℹ️ *{self.disclaimer}*")
        return "\n".join(md)


@dataclass
class DocumentCitation:
    """Precise citation to a document passage."""

    filename: str
    page_number: int
    chunk_index: int
    snippet: str


@dataclass
class DocumentAnswerResult:
    """Evidence-grounded answer to a user question using indexed documents."""

    question: str
    answer: str
    citations: list[DocumentCitation] = field(default_factory=list)
    has_sufficient_evidence: bool = True
    unsupported_notes: list[str] = field(default_factory=list)
    is_offline: bool = False
    disclaimer: str = "Answer grounded in retrieved document passages."

    def format_markdown(self) -> str:
        md = [f"### 📑 Knowledge Q&A: {self.question}", ""]

        if not self.has_sufficient_evidence:
            md.append("⚠️ **Insufficient Evidence:**")
            md.append(
                "The indexed document passages do not contain sufficient evidence to answer this question.\n"
            )
            if self.unsupported_notes:
                md.append("**Notes:**")
                for n in self.unsupported_notes:
                    md.append(f"- {n}")
                md.append("")
            return "\n".join(md)

        md.append(f"**Answer:**\n{self.answer}\n")

        if self.citations:
            md.append("**Citations & Sources:**")
            for c in self.citations:
                page_str = f", Page {c.page_number}" if c.page_number > 0 else ""
                md.append(f"- **`{c.filename}`{page_str}**: \"{c.snippet[:200]}...\"")
            md.append("")

        md.append(f"> ℹ️ *{self.disclaimer}*")
        return "\n".join(md)
