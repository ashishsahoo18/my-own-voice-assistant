"""Base abstract document reader for OLIVER 2.0 Documents & Knowledge."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

from knowledge.models import DocumentReadResult


class BaseDocumentReader(ABC):
    """Abstract interface for format-specific document text extractors."""

    @abstractmethod
    def can_read(self, file_path: Path) -> bool:
        """Return True if this reader supports the file extension / format."""
        pass

    @abstractmethod
    def read(self, file_path: Path) -> DocumentReadResult:
        """Extract pages and text from the document file."""
        pass

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of a file for content deduplication."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
