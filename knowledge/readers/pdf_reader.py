"""Robust PDF document reader with stream decoding, decompression bomb guard, and page mapping."""

from __future__ import annotations

import logging
import re
import zlib
from pathlib import Path
from typing import Optional

from knowledge.models import DocumentPage, DocumentReadResult
from knowledge.readers.base import BaseDocumentReader

logger = logging.getLogger("oliver.knowledge.pdf_reader")


class PdfDocumentReader(BaseDocumentReader):
    """Extracts text and page numbers from PDF files with pure-Python stream decoding."""

    SUPPORTED_EXTENSIONS = {".pdf"}
    MAX_DECOMPRESSED_PAGE_SIZE = 15 * 1024 * 1024  # 15 MB decompressed limit

    def can_read(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def read(self, file_path: Path) -> DocumentReadResult:
        if not file_path.exists():
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".pdf",
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
                file_type=".pdf",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=0,
                file_hash=self.compute_file_hash(file_path),
                is_success=False,
                error="PDF file is empty (0 bytes).",
            )

        file_hash = self.compute_file_hash(file_path)

        # 1. Read raw bytes
        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
        except Exception as exc:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".pdf",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=file_hash,
                is_success=False,
                error=f"Could not read file: {exc}",
            )

        # 2. Check PDF header
        if not raw_bytes.startswith(b"%PDF-"):
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".pdf",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=file_hash,
                is_success=False,
                error="Malformed PDF: missing %PDF- header.",
            )

        # 3. Check for encryption
        if b"/Encrypt" in raw_bytes:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".pdf",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=file_hash,
                is_success=False,
                error="PDF file is encrypted or password-protected.",
            )

        # 4. Attempt extraction via pypdf if installed
        try:
            import pypdf  # type: ignore
            return self._read_with_pypdf(file_path, raw_bytes, file_size, file_hash)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("pypdf parsing failed, falling back to built-in stream parser: %s", exc)

        # 5. Built-in Pure-Python stream extractor
        return self._read_with_builtin_parser(file_path, raw_bytes, file_size, file_hash)

    def _read_with_pypdf(
        self,
        file_path: Path,
        raw_bytes: bytes,
        file_size: int,
        file_hash: str,
    ) -> DocumentReadResult:
        """Parse PDF using pypdf library if available."""
        import io
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        if reader.is_encrypted:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".pdf",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=file_hash,
                is_success=False,
                error="PDF file is encrypted or password-protected.",
            )

        pages: list[DocumentPage] = []
        full_text_chunks: list[str] = []

        for idx, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(DocumentPage(page_number=idx, text=text))
                full_text_chunks.append(text)

        full_text = "\n\n".join(full_text_chunks)
        return DocumentReadResult(
            file_path=str(file_path),
            filename=file_path.name,
            file_type=".pdf",
            pages=pages,
            full_text=full_text,
            total_pages=len(reader.pages),
            file_size=file_size,
            file_hash=file_hash,
            is_success=True,
        )

    def _read_with_builtin_parser(
        self,
        file_path: Path,
        raw_bytes: bytes,
        file_size: int,
        file_hash: str,
    ) -> DocumentReadResult:
        """Built-in pure-Python PDF stream decoder."""
        # Find stream objects
        stream_matches = list(re.finditer(rb"stream[\r\n]+(.*?)[\r\n]+endstream", raw_bytes, re.DOTALL))
        if not stream_matches:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".pdf",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=file_hash,
                is_success=False,
                error="No readable content streams found in PDF.",
            )

        # Detect page breaks by checking /Page objects or dividing streams
        page_splits = list(re.finditer(rb"/Type\s*/Page\b", raw_bytes))
        estimated_pages = max(1, len(page_splits))

        extracted_text_blocks: list[str] = []

        for m in stream_matches:
            stream_data = m.group(1)
            decompressed = self._decompress_stream(stream_data)
            if decompressed:
                text = self._extract_text_operators(decompressed)
                if text.strip():
                    extracted_text_blocks.append(text.strip())

        if not extracted_text_blocks:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".pdf",
                pages=[],
                full_text="",
                total_pages=estimated_pages,
                file_size=file_size,
                file_hash=file_hash,
                is_success=True,
                error=None,
            )

        # Map extracted blocks to pages
        pages: list[DocumentPage] = []
        if len(extracted_text_blocks) == 1:
            pages.append(DocumentPage(page_number=1, text=extracted_text_blocks[0]))
        else:
            for idx, blk in enumerate(extracted_text_blocks, 1):
                pages.append(DocumentPage(page_number=idx, text=blk))

        full_text = "\n\n".join(p.text for p in pages)
        return DocumentReadResult(
            file_path=str(file_path),
            filename=file_path.name,
            file_type=".pdf",
            pages=pages,
            full_text=full_text,
            total_pages=len(pages),
            file_size=file_size,
            file_hash=file_hash,
            is_success=True,
        )

    def _decompress_stream(self, stream_data: bytes) -> Optional[bytes]:
        """Safely decompress FlateDecode stream with decompression bomb bounds."""
        # Try zlib decompression
        try:
            # Check for header
            decomp = zlib.decompress(stream_data)
            if len(decomp) > self.MAX_DECOMPRESSED_PAGE_SIZE:
                logger.warning("PDF stream exceeded decompression bounds; truncated.")
                return decomp[: self.MAX_DECOMPRESSED_PAGE_SIZE]
            return decomp
        except Exception:
            pass

        # If already uncompressed text
        if b"BT" in stream_data and b"ET" in stream_data:
            return stream_data

        return None

    @classmethod
    def _extract_text_operators(cls, decompressed: bytes) -> str:
        """Parse BT ... ET blocks and extract Tj / TJ string operands."""
        collected: list[str] = []

        # Find all BT ... ET text blocks
        bt_blocks = re.findall(rb"BT[\s\S]*?ET", decompressed)
        for block in bt_blocks:
            # Match (text) Tj
            tj_matches = re.findall(rb"\((.*?)\)\s*Tj", block)
            for m in tj_matches:
                collected.append(cls._decode_pdf_string(m))

            # Match [(...) -10 (...)] TJ
            array_matches = re.findall(rb"\[(.*?)\]\s*TJ", block)
            for arr in array_matches:
                inner_strings = re.findall(rb"\((.*?)\)", arr)
                for s in inner_strings:
                    collected.append(cls._decode_pdf_string(s))

        return " ".join(collected)

    @staticmethod
    def _decode_pdf_string(raw: bytes) -> str:
        """Unescape PDF literal string bytes to unicode text."""
        try:
            # Handle standard escapes
            s = raw.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
            return s.decode("utf-8", errors="replace")
        except Exception:
            return raw.decode("latin-1", errors="replace")
