"""Structured diff and minimal patch generator for OLIVER 2.0 Coding Assistant.

Never applies or overwrites files on disk automatically.
"""

from __future__ import annotations

import difflib
import re
from typing import Optional, Tuple

from coding.models import PatchResult


class DiffEngine:
    """Produces, validates, and simulates minimal surgical unified diff patches."""

    HUNK_HEADER_PATTERN = re.compile(
        r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?\s+\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?\s+@@"
    )

    @classmethod
    def generate_patch(
        cls,
        original_code: str,
        modified_code: str,
        file_path: Optional[str] = None,
        context_lines: int = 3,
    ) -> PatchResult:
        """Produce a standard unified diff between original and modified code."""
        orig_clean = original_code + "\n" if original_code and not original_code.endswith("\n") else original_code
        mod_clean = modified_code + "\n" if modified_code and not modified_code.endswith("\n") else modified_code
        orig_lines = orig_clean.splitlines(keepends=True)
        mod_lines = mod_clean.splitlines(keepends=True)

        from_label = f"a/{file_path}" if file_path else "a/original"
        to_label = f"b/{file_path}" if file_path else "b/modified"

        diff_gen = difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=from_label,
            tofile=to_label,
            n=context_lines,
        )
        diff_text = "".join(diff_gen)

        if not diff_text.strip():
            return PatchResult(
                patch="",
                is_valid=True,
                summary="No changes detected; original and modified code are identical.",
                original_path=file_path,
            )

        # Validate generated diff applicability against original
        is_valid, val_err = cls.validate_patch_applicability(original_code, diff_text)

        summary = cls._summarize_diff(diff_text)

        return PatchResult(
            patch=diff_text,
            is_valid=is_valid,
            validation_error=val_err,
            summary=summary,
            original_path=file_path,
        )

    @classmethod
    def validate_patch_applicability(cls, original_code: str, patch_text: str) -> Tuple[bool, Optional[str]]:
        """Verify that the patch is syntactically valid unified diff and applies cleanly in-memory."""
        if not patch_text or not patch_text.strip():
            return True, None

        patch_lines = patch_text.splitlines()
        has_header = False
        has_hunk = False

        for line in patch_lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                has_header = True
            elif cls.HUNK_HEADER_PATTERN.match(line):
                has_hunk = True

        if not has_hunk:
            return False, "Malformed patch: missing unified diff hunk header (@@ -x,y +a,b @@)."

        # In-memory dry-run patch application
        try:
            applied = cls.apply_patch_in_memory(original_code, patch_text)
            if applied is None:
                return False, "Patch could not be cleanly applied to original content (chunk context mismatch)."
            return True, None
        except Exception as exc:
            return False, f"Patch dry-run application error: {exc}"

    @classmethod
    def apply_patch_in_memory(cls, original_code: str, patch_text: str) -> Optional[str]:
        """Apply unified diff to string purely in memory without disk access.
        
        Returns modified string, or None if patch fails to apply.
        """
        orig_lines = original_code.splitlines()
        patch_lines = patch_text.splitlines()

        result_lines: list[str] = []
        orig_idx = 0

        i = 0
        while i < len(patch_lines):
            line = patch_lines[i]
            m = cls.HUNK_HEADER_PATTERN.match(line)
            if m:
                old_start = int(m.group("old_start")) - 1  # 1-indexed to 0-indexed
                if old_start > len(orig_lines):
                    return None  # Hunk start is out of bounds

                # Copy lines up to hunk start
                while orig_idx < old_start and orig_idx < len(orig_lines):
                    result_lines.append(orig_lines[orig_idx])
                    orig_idx += 1

                i += 1
                while i < len(patch_lines) and not cls.HUNK_HEADER_PATTERN.match(patch_lines[i]):
                    hunk_line = patch_lines[i]
                    if hunk_line.startswith("+"):
                        result_lines.append(hunk_line[1:])
                    elif hunk_line.startswith("-"):
                        expected_del = hunk_line[1:]
                        if orig_idx >= len(orig_lines) or orig_lines[orig_idx] != expected_del:
                            return None  # Mismatch on line to be deleted
                        orig_idx += 1
                    elif hunk_line.startswith("\\"):
                        # e.g., \ No newline at end of file
                        pass
                    elif hunk_line.startswith(" ") or hunk_line == "":
                        expected_ctx = hunk_line[1:] if hunk_line.startswith(" ") else ""
                        if orig_idx >= len(orig_lines) or (expected_ctx and orig_lines[orig_idx] != expected_ctx):
                            return None  # Context line mismatch
                        result_lines.append(orig_lines[orig_idx])
                        orig_idx += 1
                    i += 1
                continue
            i += 1

        # Copy any remaining trailing lines
        while orig_idx < len(orig_lines):
            result_lines.append(orig_lines[orig_idx])
            orig_idx += 1

        return "\n".join(result_lines)

    @classmethod
    def _summarize_diff(cls, diff_text: str) -> str:
        """Count added and removed lines."""
        added = 0
        removed = 0
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        return f"{added} line(s) added, {removed} line(s) removed."
