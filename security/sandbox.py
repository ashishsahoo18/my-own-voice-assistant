"""Path sandboxing and Windows Recycle Bin delete protection for OLIVER 2.0."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import shutil
from pathlib import Path
from typing import Optional

from core.config import get_config
from core.errors import PathSandboxViolation


# Win32 Shell API for moving files to Recycle Bin (FO_DELETE with FOF_ALLOWUNDO)
FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


class PathSandbox:
    """Validates paths against traversal, protected system directories, and symlink escapes."""

    PROTECTED_SYSTEM_DIRS = [
        Path("C:/Windows"),
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
    ]

    SENSITIVE_USER_SUBDIRS = [
        ".ssh",
        ".aws",
        ".gnupg",
        "AppData/Local/Google/Chrome/User Data",
        "AppData/Roaming/Mozilla/Firefox/Profiles",
    ]

    def __init__(self, allowed_roots: Optional[list[Path]] = None) -> None:
        cfg = get_config()
        self.allowed_roots = allowed_roots or cfg.security.allowlist_roots

    def validate_path(self, target: Path | str, allow_create_parent: bool = False) -> Path:
        """Validate that target path is inside allowed roots and not in protected system folders.

        Raises PathSandboxViolation on violation.
        """
        raw_str = str(target).strip()
        if not raw_str:
            raise PathSandboxViolation(raw_str)

        # Reject obvious traversal sequences before resolve
        if ".." in raw_str.replace("\\", "/").split("/"):
            # Still check resolved path
            pass

        try:
            path_obj = Path(target)
            resolved = path_obj.resolve()
        except Exception as exc:
            raise PathSandboxViolation(f"Cannot resolve path '{target}': {exc}")

        # Check protected Windows directories
        resolved_str = str(resolved).lower()
        for sys_dir in self.PROTECTED_SYSTEM_DIRS:
            if resolved_str.startswith(str(sys_dir.resolve()).lower()):
                raise PathSandboxViolation(
                    f"Access to protected Windows system directory denied: {resolved}"
                )

        # Check sensitive user subdirectories (.ssh, browser profiles)
        user_home = Path.home().resolve()
        for sens in self.SENSITIVE_USER_SUBDIRS:
            sens_path = (user_home / sens).resolve()
            if resolved_str.startswith(str(sens_path).lower()):
                raise PathSandboxViolation(
                    f"Access to sensitive credential directory denied: {resolved}"
                )

        # Check that path is within at least one allowed root
        is_allowed = False
        for root in self.allowed_roots:
            try:
                root_resolved = root.resolve()
                if resolved == root_resolved or root_resolved in resolved.parents:
                    is_allowed = True
                    break
            except Exception:
                continue

        if not is_allowed:
            raise PathSandboxViolation(
                f"Path '{resolved}' is outside allowed workspace directories."
            )

        return resolved

    def safe_delete(self, target: Path | str) -> tuple[bool, str]:
        """Move file or folder to the Windows Recycle Bin instead of permanent deletion."""
        resolved = self.validate_path(target)
        if not resolved.exists():
            return False, f"Target not found: {resolved}"

        # 1. Try Windows SHFileOperation (Recycle Bin)
        try:
            path_str = str(resolved) + "\0\0"  # Double null-terminated string required
            file_op = SHFILEOPSTRUCTW()
            file_op.wFunc = FO_DELETE
            file_op.pFrom = path_str
            file_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

            res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(file_op))
            if res == 0:
                return True, f"Moved '{resolved.name}' to the Recycle Bin."
        except Exception:
            pass

        # 2. Fallback to safe rename / quarantine folder if Recycle Bin API fails
        try:
            quarantine_dir = get_config().storage.base_dir / "backups" / "recycle_bin"
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            quarantine_target = quarantine_dir / f"deleted_{resolved.name}"
            shutil.move(str(resolved), str(quarantine_target))
            return True, f"Moved '{resolved.name}' to safe backup directory: {quarantine_target}."
        except Exception as exc:
            return False, f"Could not safely delete {resolved.name}: {exc}"
