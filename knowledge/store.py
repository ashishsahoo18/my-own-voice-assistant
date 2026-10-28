"""Persistent SQLite FTS5 store for documents, chunks, and BM25 passage ranking."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Optional

from knowledge.models import (
    DocumentChunk,
    DocumentChunkMatch,
    DocumentMetadata,
)
from memory.unified_db import UnifiedDatabase, get_unified_db

logger = logging.getLogger("oliver.knowledge.store")


class KnowledgeStore:
    """Persistent local knowledge base powered by SQLite FTS5 and WAL mode in oliver.db."""

    def __init__(self, db: Optional[UnifiedDatabase] = None) -> None:
        self.db = db or get_unified_db()

    def index_document(
        self,
        doc: DocumentMetadata,
        chunks: list[DocumentChunk],
    ) -> None:
        """Store document metadata and chunks into SQLite and the FTS5 search index."""
        conn = self.db.get_connection()
        with conn:
            # 1. Clean existing record with same doc_id or file_hash if present
            self._delete_internal(conn, doc.doc_id)
            cursor = conn.execute("SELECT doc_id FROM indexed_documents WHERE file_hash = ?", (doc.file_hash,))
            existing = cursor.fetchone()
            if existing:
                self._delete_internal(conn, existing[0])

            # 2. Insert document record
            conn.execute(
                """
                INSERT INTO indexed_documents
                (doc_id, file_path, filename, file_hash, file_type, file_size, total_chunks, total_pages, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc.doc_id,
                    doc.file_path,
                    doc.filename,
                    doc.file_hash,
                    doc.file_type,
                    doc.file_size,
                    len(chunks),
                    doc.total_pages,
                    json.dumps(doc.metadata),
                    doc.created_at,
                    doc.updated_at,
                ),
            )

            # 3. Insert chunks and FTS5 passage index
            for c in chunks:
                conn.execute(
                    """
                    INSERT INTO document_chunks
                    (chunk_id, doc_id, chunk_index, page_number, content, char_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c.chunk_id,
                        c.doc_id,
                        c.chunk_index,
                        c.page_number,
                        c.content,
                        c.char_count,
                        c.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO document_chunks_fts (chunk_id, doc_id, filename, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        c.chunk_id,
                        c.doc_id,
                        c.filename,
                        c.content,
                    ),
                )

    def search_passages(
        self,
        query: str,
        doc_id: Optional[str] = None,
        top_k: int = 5,
    ) -> list[DocumentChunkMatch]:
        """Search indexed passages using SQLite FTS5 BM25 ranking."""
        clean_q = query.strip()
        if not clean_q:
            return []

        conn = self.db.get_connection()
        matches: list[DocumentChunkMatch] = []

        # Sanitize query for FTS5 (escape quotes, combine terms)
        sanitized_fts_tokens = [re.sub(r'[^a-zA-Z0-9_\*]', '', t) for t in clean_q.split()]
        sanitized_fts_tokens = [t for t in sanitized_fts_tokens if t]

        if not sanitized_fts_tokens:
            return []

        fts_query = " OR ".join(sanitized_fts_tokens)

        # 1. Try FTS5 BM25 ranking
        try:
            if doc_id:
                sql = """
                    SELECT f.chunk_id, f.doc_id, f.filename, f.content, bm25(document_chunks_fts) as score,
                           c.chunk_index, c.page_number, c.char_count, c.created_at,
                           snippet(document_chunks_fts, 3, '<b>', '</b>', '...', 20) as snip
                    FROM document_chunks_fts f
                    JOIN document_chunks c ON f.chunk_id = c.chunk_id
                    WHERE document_chunks_fts MATCH ? AND f.doc_id = ?
                    ORDER BY score ASC
                    LIMIT ?
                """
                cursor = conn.execute(sql, (fts_query, doc_id, top_k))
            else:
                sql = """
                    SELECT f.chunk_id, f.doc_id, f.filename, f.content, bm25(document_chunks_fts) as score,
                           c.chunk_index, c.page_number, c.char_count, c.created_at,
                           snippet(document_chunks_fts, 3, '<b>', '</b>', '...', 20) as snip
                    FROM document_chunks_fts f
                    JOIN document_chunks c ON f.chunk_id = c.chunk_id
                    WHERE document_chunks_fts MATCH ?
                    ORDER BY score ASC
                    LIMIT ?
                """
                cursor = conn.execute(sql, (fts_query, top_k))

            for row in cursor.fetchall():
                chunk = DocumentChunk(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    chunk_index=row["chunk_index"],
                    page_number=row["page_number"],
                    content=row["content"],
                    char_count=row["char_count"],
                    filename=row["filename"],
                    created_at=row["created_at"],
                )
                score = abs(float(row["score"]))
                snip = row["snip"] or row["content"][:200]
                matches.append(DocumentChunkMatch(chunk=chunk, rank_score=score, snippet=snip))

        except sqlite3.OperationalError as exc:
            logger.warning("FTS5 query failed (%s), falling back to LIKE: %s", fts_query, exc)

        # 2. Fallback to LIKE if FTS5 returned no results
        if not matches:
            fallback_sql = """
                SELECT c.chunk_id, c.doc_id, c.chunk_index, c.page_number, c.content, c.char_count, c.created_at, d.filename
                FROM document_chunks c
                JOIN indexed_documents d ON c.doc_id = d.doc_id
                WHERE c.content LIKE ?
            """
            params: list[object] = [f"%{clean_q}%"]
            if doc_id:
                fallback_sql += " AND c.doc_id = ?"
                params.append(doc_id)
            fallback_sql += " LIMIT ?"
            params.append(top_k)

            cursor = conn.execute(fallback_sql, tuple(params))
            for row in cursor.fetchall():
                chunk = DocumentChunk(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    chunk_index=row["chunk_index"],
                    page_number=row["page_number"],
                    content=row["content"],
                    char_count=row["char_count"],
                    filename=row["filename"],
                    created_at=row["created_at"],
                )
                matches.append(DocumentChunkMatch(chunk=chunk, rank_score=1.0, snippet=chunk.content[:200]))

        return matches

    def get_document(self, doc_id: str) -> Optional[DocumentMetadata]:
        """Fetch document metadata by doc_id."""
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM indexed_documents WHERE doc_id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_metadata(row)

    def get_document_chunks(self, doc_id: str) -> list[DocumentChunk]:
        """Fetch all chunks for a document ordered by chunk_index."""
        conn = self.db.get_connection()
        cursor = conn.execute(
            """
            SELECT c.*, d.filename FROM document_chunks c
            JOIN indexed_documents d ON c.doc_id = d.doc_id
            WHERE c.doc_id = ?
            ORDER BY c.chunk_index ASC
            """,
            (doc_id,),
        )
        chunks: list[DocumentChunk] = []
        for row in cursor.fetchall():
            chunks.append(
                DocumentChunk(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    chunk_index=row["chunk_index"],
                    page_number=row["page_number"],
                    content=row["content"],
                    char_count=row["char_count"],
                    filename=row["filename"],
                    created_at=row["created_at"],
                )
            )
        return chunks

    def list_documents(self) -> list[DocumentMetadata]:
        """List all indexed documents in the knowledge base."""
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM indexed_documents ORDER BY updated_at DESC")
        return [self._row_to_metadata(row) for row in cursor.fetchall()]

    def delete_document(self, doc_id_or_name: str) -> tuple[bool, str]:
        """Remove document and its passages from the index. NEVER modifies the original file on disk."""
        conn = self.db.get_connection()
        with conn:
            # Check by doc_id first, then by filename
            cursor = conn.execute(
                "SELECT doc_id, filename FROM indexed_documents WHERE doc_id = ? OR filename = ?",
                (doc_id_or_name, doc_id_or_name),
            )
            row = cursor.fetchone()
            if not row:
                return False, f"Document '{doc_id_or_name}' not found in knowledge index."

            doc_id, filename = row[0], row[1]
            self._delete_internal(conn, doc_id)
            return True, f"Successfully removed '{filename}' (ID: {doc_id}) from knowledge index. Original file is untouched."

    def clear_index(self) -> tuple[bool, str]:
        """Remove all documents from knowledge index. Original files remain untouched on disk."""
        conn = self.db.get_connection()
        with conn:
            conn.execute("DELETE FROM document_chunks_fts;")
            conn.execute("DELETE FROM document_chunks;")
            conn.execute("DELETE FROM indexed_documents;")
        return True, "Knowledge index cleared. All source files remain intact."

    def _delete_internal(self, conn: sqlite3.Connection, doc_id: str) -> None:
        """Helper to delete all chunks, FTS entries, and doc record."""
        conn.execute("DELETE FROM document_chunks_fts WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM document_chunks WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM indexed_documents WHERE doc_id = ?", (doc_id,))

    @staticmethod
    def _row_to_metadata(row: sqlite3.Row) -> DocumentMetadata:
        meta_dict = {}
        try:
            if row["metadata_json"]:
                meta_dict = json.loads(row["metadata_json"])
        except Exception:
            pass

        return DocumentMetadata(
            doc_id=row["doc_id"],
            filename=row["filename"],
            file_path=row["file_path"],
            file_type=row["file_type"],
            file_size=row["file_size"],
            file_hash=row["file_hash"],
            total_chunks=row["total_chunks"],
            total_pages=row["total_pages"],
            metadata=meta_dict,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
