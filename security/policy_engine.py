"""Central Policy Engine for OLIVER 2.0."""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field

from core.config import get_config
from core.errors import PathSandboxViolation, PolicyDenied
from core.logging import get_audit_logger
from security.confirmation import ConfirmationManager, get_confirmation_manager
from security.kill_switch import KillSwitch, RateLimiter, get_kill_switch, get_rate_limiter
from security.sandbox import PathSandbox

logger = logging.getLogger("oliver.security.policy")


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    NEED_CONFIRM = "NEED_CONFIRM"
    DENY = "DENY"


class PolicyDecision(BaseModel):
    """Result of policy evaluation."""

    decision: PolicyDecisionType
    reason: str = ""
    summary: str = ""
    token: Optional[str] = None
    risk_level: int = 0
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        return self.decision == PolicyDecisionType.ALLOW

    @property
    def is_need_confirm(self) -> bool:
        return self.decision == PolicyDecisionType.NEED_CONFIRM

    @property
    def is_denied(self) -> bool:
        return self.decision == PolicyDecisionType.DENY


class PolicyEngine:
    """Single central policy gate for all tool invocations in OLIVER 2.0."""

    def __init__(
        self,
        sandbox: Optional[PathSandbox] = None,
        confirmation_manager: Optional[ConfirmationManager] = None,
        kill_switch: Optional[KillSwitch] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self.sandbox = sandbox or PathSandbox()
        self.confirmation_mgr = confirmation_manager or get_confirmation_manager()
        self.kill_switch = kill_switch or get_kill_switch()
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.config = get_config()

    def evaluate(
        self,
        tool_name: str,
        risk_level: int,
        arguments: Optional[dict[str, Any]] = None,
        user_confirmed: bool = False,
        confirmation_token: Optional[str] = None,
    ) -> PolicyDecision:
        """Evaluate action against security policy rules.

        The LLM NEVER makes the permission decision.
        """
        args = arguments or {}
        audit = get_audit_logger()

        # 1. Kill Switch Check
        if self.kill_switch.is_active:
            reason = f"Emergency kill switch is engaged ({self.kill_switch.reason}). All actions blocked."
            audit.record_event("POLICY_EVAL", tool_name, risk_level, "DENIED", {"reason": reason})
            return PolicyDecision(
                decision=PolicyDecisionType.DENY,
                reason=reason,
                risk_level=risk_level,
            )

        # 2. Arbitrary Command Execution Check
        if "shell" in tool_name.lower() or "cmd" in tool_name.lower():
            if not self.config.security.allow_arbitrary_commands:
                reason = "Arbitrary command execution is disabled by default for security."
                audit.record_event("POLICY_EVAL", tool_name, risk_level, "DENIED", {"reason": reason})
                return PolicyDecision(
                    decision=PolicyDecisionType.DENY,
                    reason=reason,
                    risk_level=risk_level,
                )

        # 3. Path Sandboxing Check
        is_file_tool = any(k in tool_name.lower() for k in ("file", "folder", "dir", "path"))
        path_keys = ["path", "file_path", "folder_path", "directory", "source", "destination", "old_path", "new_path"]
        if is_file_tool:
            path_keys.append("target")

        for pkey in path_keys:
            if pkey in args and isinstance(args[pkey], (str, Path)) and str(args[pkey]).strip():
                val_str = str(args[pkey]).strip()
                if "@" in val_str or val_str.startswith(("http://", "https://")):
                    continue
                try:
                    self.sandbox.validate_path(val_str)
                except PathSandboxViolation as psv:
                    reason = str(psv)
                    audit.record_event("POLICY_EVAL", tool_name, risk_level, "DENIED", {"path_error": reason})
                    return PolicyDecision(
                        decision=PolicyDecisionType.DENY,
                        reason=reason,
                        risk_level=risk_level,
                    )

        # 4. Rate Limiting Check for Sensitive/Dangerous Actions (Risk >= 2)
        if risk_level >= 2:
            if not self.rate_limiter.allow(tool_name, max_requests=10, window_seconds=60.0):
                reason = f"Rate limit exceeded for sensitive tool '{tool_name}'. Please wait."
                audit.record_event("POLICY_EVAL", tool_name, risk_level, "DENIED", {"reason": reason})
                return PolicyDecision(
                    decision=PolicyDecisionType.DENY,
                    reason=reason,
                    risk_level=risk_level,
                )

        # 5. Risk Level 0 (SAFE) - Auto-allow
        if risk_level == 0:
            return PolicyDecision(decision=PolicyDecisionType.ALLOW, risk_level=0)

        # 6. Risk Level 1 (LOW) - Auto-allow with audit log
        if risk_level == 1:
            audit.record_event("POLICY_EVAL", tool_name, risk_level, "ALLOWED", {"args": args})
            return PolicyDecision(decision=PolicyDecisionType.ALLOW, risk_level=1)

        # 7. Risk Level 2 (SENSITIVE) and Risk Level 3 (DANGEROUS)
        # Check if already verified with token
        if confirmation_token:
            is_valid, expl = self.confirmation_mgr.verify_and_consume(confirmation_token, "yes")
            if is_valid:
                audit.record_event("POLICY_EVAL", tool_name, risk_level, "CONFIRMED_AND_ALLOWED", {"token": confirmation_token})
                return PolicyDecision(
                    decision=PolicyDecisionType.ALLOW,
                    reason="Confirmation token successfully verified and consumed.",
                    risk_level=risk_level,
                )
            else:
                audit.record_event("POLICY_EVAL", tool_name, risk_level, "DENIED_INVALID_TOKEN", {"token": confirmation_token, "reason": expl})
                return PolicyDecision(
                    decision=PolicyDecisionType.DENY,
                    reason=f"Confirmation failed: {expl}",
                    risk_level=risk_level,
                )

        if user_confirmed:
            audit.record_event("POLICY_EVAL", tool_name, risk_level, "CONFIRMED_AND_ALLOWED", {"legacy_confirmed": True})
            return PolicyDecision(
                decision=PolicyDecisionType.ALLOW,
                reason="User confirmed execution.",
                risk_level=risk_level,
            )

        # Needs explicit user confirmation: build exact-effect preview summary
        summary = self._build_exact_effect_summary(tool_name, risk_level, args)
        req = self.confirmation_mgr.create_request(
            action=tool_name,
            risk_level=risk_level,
            summary=summary,
            details=args,
            timeout_s=self.config.security.confirmation_timeout_seconds,
        )

        return PolicyDecision(
            decision=PolicyDecisionType.NEED_CONFIRM,
            summary=summary,
            token=req.token,
            risk_level=risk_level,
            details=args,
        )

    def _build_exact_effect_summary(self, tool_name: str, risk_level: int, args: dict[str, Any]) -> str:
        """Construct unambiguous exact-effect preview string showing target, operation, and parameters."""
        lowered = tool_name.lower()

        if "shutdown" in lowered:
            return "Shutdown the computer workstation completely."
        if "restart" in lowered and "explorer" not in lowered:
            return "Reboot the computer workstation."
        if "sleep" in lowered:
            return "Put the workstation into sleep mode."
        if "delete_file" in lowered or "delete" in lowered:
            target = args.get("path") or args.get("target") or "file"
            return f"Delete '{target}' (moves to Windows Recycle Bin)."
        if "delete_folder" in lowered:
            target = args.get("path") or args.get("target") or "folder"
            return f"Delete folder '{target}' and its contents (moves to Windows Recycle Bin)."
        if "whatsapp" in lowered:
            recipient = args.get("recipient") or args.get("number") or "contact"
            msg = args.get("message") or ""
            return f"Send WhatsApp message to '{recipient}': \"{msg}\""
        if "email" in lowered:
            recipient = args.get("to_email") or args.get("recipient") or "email address"
            subject = args.get("subject") or "Message from OLIVER"
            return f"Send email to '{recipient}' with subject '{subject}'"
        if "move" in lowered:
            return f"Move '{args.get('source')}' to '{args.get('destination')}'"
        if "rename" in lowered:
            return f"Rename '{args.get('old_path')}' to '{args.get('new_path')}'"

        return f"Execute sensitive operation '{tool_name}' with parameters {args}"


_global_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    """Return central PolicyEngine singleton."""
    global _global_policy_engine
    if _global_policy_engine is None:
        _global_policy_engine = PolicyEngine()
    return _global_policy_engine
