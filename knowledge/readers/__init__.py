"""Document readers package for OLIVER 2.0 Documents & Knowledge."""

from __future__ import annotations

from knowledge.readers.base import BaseDocumentReader
from knowledge.readers.factory import DocumentReaderFactory
from knowledge.readers.json_reader import JsonDocumentReader
from knowledge.readers.pdf_reader import PdfDocumentReader
from knowledge.readers.text_reader import TextDocumentReader

__all__ = [
    "BaseDocumentReader",
    "TextDocumentReader",
    "JsonDocumentReader",
    "PdfDocumentReader",
    "DocumentReaderFactory",
]
