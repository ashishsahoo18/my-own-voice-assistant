"""Concrete post-execution verifiers for OLIVER 2.0.

Produces real observable evidence (filesystem, process table, network ACK).
Never invents evidence and never relies on LLM statements.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("oliver.execution.verifiers")


class VerificationResult:
    """Result returned by a concrete verifier."""

    def __init__(
        self,
        status: str,
        evidence: Optional[dict[str, Any]] = None,
        message: str = "",
    ) -> None:
        self.status = status  # VERIFIED, UNVERIFIED, FAILED
        self.evidence = evidence or {}
        self.message = message


class BaseVerifier:
    """Base contract for domain-specific post-execution verifiers."""

    def verify(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_result: Any,
    ) -> VerificationResult:
        raise NotImplementedError


class FileVerifier(BaseVerifier):
    """Verifies filesystem modifications using concrete OS filesystem state."""

    def verify(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_result: Any,
    ) -> VerificationResult:
        lowered = tool_name.lower()
        target = (
            arguments.get("path")
            or arguments.get("file_path")
            or arguments.get("folder_path")
            or arguments.get("target")
        )

        if not target:
            return VerificationResult(
                status="UNVERIFIED",
                evidence={"error": "No file path parameter in arguments to verify"},
                message="File operation completed but path target was omitted.",
            )

        target_path = Path(str(target)).resolve()

        # 1. File Creation Verification
        if ("create" in lowered and "file" in lowered) or "write_file" in lowered:
            if target_path.exists() and target_path.is_file():
                stat = target_path.stat()
                return VerificationResult(
                    status="VERIFIED",
                    evidence={
                        "path": str(target_path),
                        "exists": True,
                        "is_file": True,
                        "size_bytes": stat.st_size,
                        "modified_at": stat.st_mtime,
                    },
                    message=f"Verified file exists: {target_path.name} ({stat.st_size} bytes).",
                )
            return VerificationResult(
                status="FAILED",
                evidence={"path": str(target_path), "exists": False},
                message=f"File creation verification failed: {target_path} not found.",
            )

        # 2. Folder Creation Verification
        if ("create" in lowered and "folder" in lowered) or "mkdir" in lowered:
            if target_path.exists() and target_path.is_dir():
                return VerificationResult(
                    status="VERIFIED",
                    evidence={
                        "path": str(target_path),
                        "exists": True,
                        "is_dir": True,
                    },
                    message=f"Verified folder exists: {target_path.name}.",
                )
            return VerificationResult(
                status="FAILED",
                evidence={"path": str(target_path), "exists": False},
                message=f"Folder creation verification failed: {target_path} not found.",
            )

        # 3. File / Folder Deletion Verification
        if "delete" in lowered or "remove" in lowered:
            if not target_path.exists():
                return VerificationResult(
                    status="VERIFIED",
                    evidence={
                        "path": str(target_path),
                        "absent_from_target": True,
                        "exists": False,
                    },
                    message=f"Verified deletion: '{target_path.name}' is absent from path.",
                )
            return VerificationResult(
                status="FAILED",
                evidence={"path": str(target_path), "still_exists": True},
                message=f"Deletion verification failed: '{target_path.name}' still exists.",
            )

        # 4. Move / Rename Verification
        if "rename" in lowered or "move" in lowered:
            dest = arguments.get("destination") or arguments.get("new_path")
            if dest:
                dest_path = Path(str(dest)).resolve()
                if dest_path.exists() and not target_path.exists():
                    return VerificationResult(
                        status="VERIFIED",
                        evidence={
                            "source_absent": True,
                            "destination_exists": True,
                            "dest_path": str(dest_path),
                        },
                        message=f"Verified move: target now exists at {dest_path.name}.",
                    )
            return VerificationResult(
                status="UNVERIFIED",
                evidence={"target": str(target_path)},
                message="Move/rename could not be completely verified.",
            )

        # 5. Read / List / Info Operations
        if target_path.exists():
            return VerificationResult(
                status="VERIFIED",
                evidence={"target_exists": True, "path": str(target_path)},
                message=f"Verified target exists: {target_path.name}.",
            )

        return VerificationResult(
            status="UNVERIFIED",
            evidence={"path": str(target_path), "exists": False},
            message=f"Target file {target_path.name} was not found on disk.",
        )


class ProcessVerifier(BaseVerifier):
    """Verifies application launch by checking the operating system process table."""

    COMMON_APP_EXES = {
        "notepad": ["notepad.exe"],
        "calculator": ["calculatorapp.exe", "calc.exe"],
        "calc": ["calculatorapp.exe", "calc.exe"],
        "paint": ["mspaint.exe"],
        "chrome": ["chrome.exe"],
        "firefox": ["firefox.exe"],
        "code": ["code.exe"],
        "vscode": ["code.exe"],
        "cmd": ["cmd.exe"],
        "powershell": ["powershell.exe", "pwsh.exe"],
        "explorer": ["explorer.exe"],
    }

    def verify(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_result: Any,
    ) -> VerificationResult:
        app_target = str(
            arguments.get("app_name")
            or arguments.get("target")
            or arguments.get("name")
            or ""
        ).strip().lower()

        if not app_target or not psutil:
            return VerificationResult(
                status="UNVERIFIED",
                evidence={"psutil_available": bool(psutil), "target": app_target},
                message=f"Application launch command issued for '{app_target}'; process state could not be inspected.",
            )

        expected_exes = self.COMMON_APP_EXES.get(app_target, [f"{app_target}.exe", app_target])

        # Short polling window (up to 0.5s) to allow process initialization
        start_time = time.time()
        matching_procs = []

        while time.time() - start_time < 0.6:
            matching_procs = []
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    pname = (proc.info["name"] or "").lower()
                    if any(exp in pname for exp in expected_exes):
                        matching_procs.append({
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if matching_procs:
                break
            time.sleep(0.1)

        if matching_procs:
            return VerificationResult(
                status="VERIFIED",
                evidence={
                    "process_found": True,
                    "target": app_target,
                    "processes": matching_procs[:3],
                },
                message=f"Verified process running for '{app_target}' (PID {matching_procs[0]['pid']}).",
            )

        return VerificationResult(
            status="UNVERIFIED",
            evidence={"process_found": False, "target": app_target},
            message=f"Application '{app_target}' launched, but process was not detected in active table.",
        )


class CommunicationVerifier(BaseVerifier):
    """Verifies communication actions honestly without inventing delivery confirmations."""

    def verify(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_result: Any,
    ) -> VerificationResult:
        lowered = tool_name.lower()

        # WhatsApp: UI Automation can queue the message, but delivery receipts cannot be verified
        if "whatsapp" in lowered:
            return VerificationResult(
                status="UNVERIFIED",
                evidence={
                    "channel": "whatsapp",
                    "dispatched_to_client": True,
                    "delivery_receipt_supported": False,
                },
                message="WhatsApp message dispatched to desktop app; delivery receipt cannot be confirmed.",
            )

        # Email: Check if raw result contains real SMTP server ACK
        if "email" in lowered:
            raw_str = str(raw_result).lower()
            if "250" in raw_str or "smtp ok" in raw_str or "sent successfully" in raw_str:
                return VerificationResult(
                    status="VERIFIED",
                    evidence={
                        "channel": "email",
                        "smtp_server_ack": True,
                        "recipient": arguments.get("to_email") or arguments.get("recipient"),
                    },
                    message="Email sent and confirmed by SMTP server response.",
                )
            return VerificationResult(
                status="UNVERIFIED",
                evidence={
                    "channel": "email",
                    "smtp_server_ack": False,
                },
                message="Email queued or dispatched without definitive SMTP delivery ACK.",
            )

        return VerificationResult(
            status="UNVERIFIED",
            evidence={"channel": "unknown"},
            message="Communication dispatched without verifiable delivery evidence.",
        )


class GenericVerifier(BaseVerifier):
    """Default verifier for information, query, and echo operations."""

    def verify(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_result: Any,
    ) -> VerificationResult:
        msg = raw_result.message if hasattr(raw_result, "message") else str(raw_result)
        if raw_result is not None and str(msg).strip():
            return VerificationResult(
                status="VERIFIED",
                evidence={"output_received": True, "length": len(str(msg))},
                message=str(msg),
            )
        return VerificationResult(
            status="UNVERIFIED",
            evidence={"output_received": False},
            message="Operation completed with no inspectable output.",
        )


class VerifierRegistry:
    """Dispatches tool execution results to the appropriate domain verifier."""

    def __init__(self) -> None:
        self.file_verifier = FileVerifier()
        self.process_verifier = ProcessVerifier()
        self.communication_verifier = CommunicationVerifier()
        self.generic_verifier = GenericVerifier()

    def get_verifier(self, tool_name: str) -> BaseVerifier:
        lowered = tool_name.lower()
        if lowered.startswith("files.") or "file" in lowered or "folder" in lowered:
            return self.file_verifier
        if "open_app" in lowered or "launch" in lowered or "process" in lowered:
            return self.process_verifier
        if "whatsapp" in lowered or "email" in lowered or lowered.startswith("communication."):
            return self.communication_verifier
        return self.generic_verifier
