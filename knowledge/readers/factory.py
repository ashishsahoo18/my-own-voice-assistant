"""Document reader factory for format resolution and dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from knowledge.readers.base import BaseDocumentReader
from knowledge.readers.json_reader import JsonDocumentReader
from knowledge.readers.pdf_reader import PdfDocumentReader
from knowledge.readers.text_reader import TextDocumentReader


class DocumentReaderFactory:
    """Dispatches appropriate document reader for supported formats."""

    READERS: list[BaseDocumentReader] = [
        TextDocumentReader(),
        JsonDocumentReader(),
        PdfDocumentReader(),
    ]

    @classmethod
    def get_reader(cls, file_path: Path | str) -> Optional[BaseDocumentReader]:
        """Return reader instance capable of reading file, or None if unsupported."""
        p = Path(file_path)
        for reader in cls.READERS:
            if reader.can_read(p):
                return reader
        return None

    @classmethod
    def is_supported(cls, file_path: Path | str) -> bool:
        """Return True if file extension is supported."""
        return cls.get_reader(file_path) is not None
