"""JSON document reader with structured flattening and depth limits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowledge.models import DocumentPage, DocumentReadResult
from knowledge.readers.base import BaseDocumentReader


class JsonDocumentReader(BaseDocumentReader):
    """Extracts searchable textual structure from JSON files."""

    SUPPORTED_EXTENSIONS = {".json"}

    def can_read(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def read(self, file_path: Path) -> DocumentReadResult:
        if not file_path.exists():
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".json",
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
                file_type=".json",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=0,
                file_hash=self.compute_file_hash(file_path),
                is_success=False,
                error="JSON file is empty (0 bytes).",
            )

        file_hash = self.compute_file_hash(file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".json",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=file_hash,
                is_success=False,
                error=f"Malformed JSON syntax: {exc}",
            )
        except Exception as exc:
            return DocumentReadResult(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=".json",
                pages=[],
                full_text="",
                total_pages=0,
                file_size=file_size,
                file_hash=file_hash,
                is_success=False,
                error=f"Error reading JSON: {exc}",
            )

        flattened_lines: list[str] = []
        self._flatten_json(data, "", flattened_lines, depth=0, max_depth=8)

        text_content = "\n".join(flattened_lines)
        if not text_content.strip():
            text_content = "{}"

        pages = [DocumentPage(page_number=1, text=text_content)]

        return DocumentReadResult(
            file_path=str(file_path),
            filename=file_path.name,
            file_type=".json",
            pages=pages,
            full_text=text_content,
            total_pages=1,
            file_size=file_size,
            file_hash=file_hash,
            is_success=True,
        )

    def _flatten_json(
        self,
        obj: Any,
        prefix: str,
        lines: list[str],
        depth: int = 0,
        max_depth: int = 8,
    ) -> None:
        """Recursively convert nested JSON into readable 'key: value' statements."""
        if depth > max_depth or len(lines) > 2000:
            return

        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = f"{prefix}.{k}" if prefix else str(k)
                if isinstance(v, (dict, list)):
                    self._flatten_json(v, new_key, lines, depth + 1, max_depth)
                else:
                    lines.append(f"{new_key}: {v}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_key = f"{prefix}[{i}]"
                if isinstance(item, (dict, list)):
                    self._flatten_json(item, new_key, lines, depth + 1, max_depth)
                else:
                    lines.append(f"{new_key}: {item}")
        else:
            lines.append(f"{prefix}: {obj}" if prefix else str(obj))
