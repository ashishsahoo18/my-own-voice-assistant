"""OLIVER 2.0 Documents & Knowledge Assistant package.

Provides local multi-format document reading, bounded chunking,
persistent SQLite FTS5 BM25 search, grounded summaries, and Q&A with citations.
"""

from __future__ import annotations

from knowledge.chunker import DocumentChunker
from knowledge.models import (
    DocumentAnswerResult,
    DocumentChunk,
    DocumentCitation,
    DocumentMetadata,
    DocumentReadResult,
    DocumentSearchResult,
    DocumentSummaryResult,
)
from knowledge.readers.factory import DocumentReaderFactory
from knowledge.security import DocumentSecurity
from knowledge.service import KnowledgeService
from knowledge.store import KnowledgeStore

__all__ = [
    "KnowledgeService",
    "KnowledgeStore",
    "DocumentSecurity",
    "DocumentChunker",
    "DocumentReaderFactory",
    "DocumentMetadata",
    "DocumentChunk",
    "DocumentReadResult",
    "DocumentSearchResult",
    "DocumentSummaryResult",
    "DocumentAnswerResult",
    "DocumentCitation",
]
