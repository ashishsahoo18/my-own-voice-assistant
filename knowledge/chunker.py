"""Bounded text chunker with sliding window and metadata preservation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from knowledge.models import DocumentChunk, DocumentReadResult


class DocumentChunker:
    """Splits extracted document pages into bounded passages preserving source metadata."""

    DEFAULT_CHUNK_SIZE = 600
    DEFAULT_OVERLAP = 100
    MAX_CHUNKS_PER_DOCUMENT = 500

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
        max_chunks: int = MAX_CHUNKS_PER_DOCUMENT,
    ) -> None:
        self.chunk_size = chunk_size
        self.overlap = min(overlap, chunk_size // 2)
        self.max_chunks = max_chunks

    def chunk_document(
        self,
        doc_read: DocumentReadResult,
        doc_id: str,
    ) -> list[DocumentChunk]:
        """Split document pages into bounded chunks preserving page and source filename."""
        chunks: list[DocumentChunk] = []
        now = datetime.now().isoformat()
        chunk_idx = 0

        for page in doc_read.pages:
            page_text = page.text.strip()
            if not page_text:
                continue

            page_chunks = self._chunk_text(page_text)
            for text_chunk in page_chunks:
                if len(chunks) >= self.max_chunks:
                    break

                chunk_id = f"{doc_id}_c{chunk_idx}"
                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        chunk_index=chunk_idx,
                        page_number=page.page_number,
                        content=text_chunk,
                        char_count=len(text_chunk),
                        filename=doc_read.filename,
                        created_at=now,
                    )
                )
                chunk_idx += 1

            if len(chunks) >= self.max_chunks:
                break

        return chunks

    def _chunk_text(self, text: str) -> list[str]:
        """Split a block of text into bounded passages with overlap."""
        if len(text) <= self.chunk_size:
            return [text]

        results: list[str] = []
        start = 0
        total_len = len(text)

        while start < total_len:
            end = min(start + self.chunk_size, total_len)

            # Try to break at a natural sentence or paragraph boundary
            if end < total_len:
                # Look backwards for paragraph or sentence end
                boundary = -1
                search_region = text[max(start, end - 150) : end]

                # Paragraph break
                p_match = [m.start() for m in re.finditer(r"\n\n+", search_region)]
                if p_match:
                    boundary = max(start, end - 150) + p_match[-1] + 2
                else:
                    # Sentence break
                    s_match = [m.start() for m in re.finditer(r"[.!?]\s+", search_region)]
                    if s_match:
                        boundary = max(start, end - 150) + s_match[-1] + 2
                    else:
                        # Space break
                        w_match = search_region.rfind(" ")
                        if w_match != -1:
                            boundary = max(start, end - 150) + w_match + 1

                if boundary > start:
                    end = boundary

            chunk_str = text[start:end].strip()
            if chunk_str:
                results.append(chunk_str)

            if end >= total_len:
                break

            # Slide forward by (chunk length - overlap)
            start = max(start + 1, end - self.overlap)

        return results
