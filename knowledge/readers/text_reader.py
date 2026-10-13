"""Plain text and Markdown document reader with encoding autodetection."""

from __future__ import annotations

import os
from pathlib import Path

from knowledge.models import DocumentPage, DocumentReadResult
from knowledge.readers.base import BaseDocumentReader


class TextDocumentReader(BaseDocumentReader):
    """Extracts text from .txt and .md files with robust encoding fallback."""

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".rst"}

    def can_read(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def read(self, file_path: Path) -> DocumentReadResult:
        if not file_path.exists():
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=file_path.suffix.lower(),
                pages=[],
                full_text="",
                total_pages=0,
                file_size=0,
                file_hash="",
                is_success=False,
                error="File does not exist.",
            )

        file_size = file_path.stat().st_size
        if file_size == 0:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=file_path.suffix.lower(),
                pages=[],
                full_text="",
                total_pages=0,
                file_size=0,
                file_hash=self.compute_file_hash(file_path),
                is_success=False,
                error="File is empty (0 bytes).",
            )

        # Encodings to try
        encodings = ["utf-8", "utf-8-sig", "utf-16", "latin-1", "cp1252"]
        content = ""
        read_success = False

        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read()
                read_success = True
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if not read_success:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=file_path.suffix.lower(),
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=self.compute_file_hash(file_path),
                is_success=False,
                error="Could not decode text file with supported encodings.",
            )

        file_hash = self.compute_file_hash(file_path)

        # Split large markdown/text into section pages if section dividers exist
        sections = [s.strip() for s in content.split("\n\n---\n\n") if s.strip()]
        if len(sections) <= 1:
            pages = [DocumentPage(page_number=1, text=content)]
        else:
            pages = [DocumentPage(page_number=i + 1, text=sec) for i, sec in enumerate(sections)]

        return DocumentReadResult(
            file_path=str(file_path),
            filename=file_path.name,
            file_type=file_path.suffix.lower(),
            pages=pages,
            full_text=content,
            total_pages=len(pages),
            file_size=file_size,
            file_hash=file_hash,
            is_success=True,
        )
