"""Documents & Knowledge Skill for OLIVER 2.0.

Provides tools for indexing, searching, summarizing, and questioning local documents
with source citations and persistent SQLite FTS5 search.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from knowledge.service import KnowledgeService
from skills.base import BaseSkill, SkillManifest, ToolResult, ToolRiskLevel, ToolSpec

logger = logging.getLogger("oliver.skills.knowledge")


class KnowledgeSkill(BaseSkill):
    """Documents & Knowledge skill providing local parsing, FTS5 retrieval, and cited Q&A."""

    def __init__(self, service: Optional[KnowledgeService] = None) -> None:
        super().__init__()
        self.service = service or KnowledgeService()

    def get_manifest(self) -> SkillManifest:
        return SkillManifest(
            name="knowledge",
            version="1.0.0",
            description="Manage local documents and knowledge: index TXT/MD/JSON/PDF files, search passages with BM25 ranking, summarize content, and answer questions with citations.",
            triggers=[
                "index document",
                "index file",
                "search document",
                "search knowledge",
                "summarize document",
                "ask document",
                "list documents",
                "delete document index",
            ],
            dependencies=[],
        )

    def get_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="knowledge.index_file",
                description="Index a local TXT, MD, JSON, or PDF file into the local persistent knowledge base.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.index_file,
            ),
            ToolSpec(
                name="knowledge.search",
                description="Search indexed document passages using SQLite FTS5 with BM25 ranking.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.search,
            ),
            ToolSpec(
                name="knowledge.summarize_document",
                description="Summarize an indexed document and extract key findings.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.summarize_document,
            ),
            ToolSpec(
                name="knowledge.ask_document",
                description="Answer questions grounded in indexed documents with filename and page citations.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.ask_document,
            ),
            ToolSpec(
                name="knowledge.list_documents",
                description="List all indexed documents in the local knowledge base.",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.list_documents,
            ),
            ToolSpec(
                name="knowledge.delete_document_index",
                description="Remove a document from the search index (never deletes original files on disk).",
                risk_level=ToolRiskLevel.SAFE,
                handler=self.delete_document_index,
            ),
        ]

    def index_file(self, file_path: str) -> ToolResult:
        """Index a document file into the persistent SQLite FTS5 knowledge store."""
        clean_path = (file_path or "").strip()
        if not clean_path:
            return ToolResult(status="FAILED", message="File path cannot be empty.")

        success, msg, doc = self.service.index_file(clean_path)
        status = "SUCCESS" if success else "FAILED"
        data = {
            "doc_id": doc.doc_id if doc else None,
            "filename": doc.filename if doc else None,
            "total_chunks": doc.total_chunks if doc else 0,
            "total_pages": doc.total_pages if doc else 0,
        }
        return ToolResult(status=status, message=msg, data=data)

    def search(self, query: str, doc_id: Optional[str] = None, top_k: int = 5) -> ToolResult:
        """Search passages across indexed documents."""
        clean_q = (query or "").strip()
        if not clean_q:
            return ToolResult(status="FAILED", message="Search query cannot be empty.")

        res = self.service.search(clean_q, doc_id=doc_id, top_k=top_k)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={"total_matches": res.total_matches, "query": res.query},
        )

    def summarize_document(self, file_path_or_id: str) -> ToolResult:
        """Summarize an indexed document."""
        clean_target = (file_path_or_id or "").strip()
        if not clean_target:
            return ToolResult(status="FAILED", message="Target document cannot be empty.")

        res = self.service.summarize(clean_target)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={
                "doc_id": res.doc_id,
                "filename": res.filename,
                "total_pages": res.total_pages,
                "is_offline": res.is_offline,
            },
        )

    def ask_document(self, question: str, doc_id: Optional[str] = None) -> ToolResult:
        """Answer questions with citations using retrieved passages."""
        clean_q = (question or "").strip()
        if not clean_q:
            return ToolResult(status="FAILED", message="Question cannot be empty.")

        res = self.service.ask(clean_q, doc_id=doc_id)
        return ToolResult(
            status="SUCCESS",
            message=res.format_markdown(),
            data={
                "has_sufficient_evidence": res.has_sufficient_evidence,
                "citations_count": len(res.citations),
                "is_offline": res.is_offline,
            },
        )

    def list_documents(self) -> ToolResult:
        """List all indexed documents."""
        docs = self.service.list_documents()
        if not docs:
            return ToolResult(
                status="SUCCESS",
                message="No documents currently indexed in the knowledge base.",
                data={"documents": []},
            )

        md = ["### 📚 Indexed Knowledge Documents", ""]
        for i, d in enumerate(docs, 1):
            size_kb = d.file_size / 1024
            pages_str = f"{d.total_pages} page(s), " if d.total_pages > 1 else ""
            md.append(
                f"**{i}. `{d.filename}`** (ID: `{d.doc_id}`)\n"
                f"   - Type: `{d.file_type}`, Size: {size_kb:.1f} KB\n"
                f"   - Content: {pages_str}{d.total_chunks} passage chunks\n"
                f"   - Indexed: {d.created_at[:19]}"
            )
        md.append("")
        return ToolResult(
            status="SUCCESS",
            message="\n".join(md),
            data={"count": len(docs), "documents": [d.doc_id for d in docs]},
        )

    def delete_document_index(self, doc_id_or_name: str) -> ToolResult:
        """Remove document passages from search index without modifying original files."""
        clean_target = (doc_id_or_name or "").strip()
        if not clean_target:
            return ToolResult(status="FAILED", message="Document identifier cannot be empty.")

        success, msg = self.service.delete_document(clean_target)
        status = "SUCCESS" if success else "FAILED"
        return ToolResult(status=status, message=msg)
