"""Action-bound confirmation manager with exact-effect previews and single-use tokens."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field

from core.logging import get_audit_logger


class ConfirmationRequest(BaseModel):
    """Action-bound confirmation token specification."""

    token: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: str = Field(description="Action identifier, e.g. 'windows.shutdown'")
    risk_level: int = Field(description="Risk level 2 (SENSITIVE) or 3 (DANGEROUS)")
    summary: str = Field(description="Exact-effect human preview")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured action parameters")
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(description="Timestamp when token expires")
    is_consumed: bool = Field(default=False)


class ConfirmationManager:
    """Manages creation, verification, consumption, and expiration of confirmation tokens."""

    AFFIRMATIVE_GRAMMAR = {"yes", "y", "confirm", "approve", "proceed", "yes confirm", "yes do it"}
    NEGATIVE_GRAMMAR = {"no", "n", "cancel", "deny", "abort", "stop", "nevermind"}

    def __init__(self, default_timeout_s: float = 30.0) -> None:
        self.default_timeout_s = default_timeout_s
        self._pending_tokens: dict[str, ConfirmationRequest] = {}
        self._consumed_tokens: set[str] = set()

    def create_request(
        self,
        action: str,
        risk_level: int,
        summary: str,
        details: Optional[dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> ConfirmationRequest:
        """Create a new action-bound confirmation request."""
        ttl = timeout_s if timeout_s is not None else self.default_timeout_s
        now = time.time()
        req = ConfirmationRequest(
            action=action,
            risk_level=risk_level,
            summary=summary,
            details=details or {},
            created_at=now,
            expires_at=now + ttl,
            is_consumed=False,
        )
        self._pending_tokens[req.token] = req

        # Audit record
        audit = get_audit_logger()
        audit.record_event(
            event_type="CONFIRMATION_CREATED",
            action=action,
            risk_level=risk_level,
            status="PENDING",
            details={"token": req.token, "summary": summary, "params": req.details},
        )
        return req

    def verify_and_consume(self, token: str, user_response: str) -> tuple[bool, str]:
        """Verify token and consume it. Tokens are strictly single-use and cannot be reused.

        Returns (is_approved, explanation).
        """
        clean_token = token.strip()
        if clean_token in self._consumed_tokens:
            return False, "Confirmation token has already been consumed (re-use prevented)."

        req = self._pending_tokens.get(clean_token)

        if not req:
            return False, "Invalid or non-existent confirmation token."

        # Mark as consumed immediately to prevent race conditions / reuse
        req.is_consumed = True
        self._consumed_tokens.add(clean_token)
        self._pending_tokens.pop(clean_token, None)

        now = time.time()
        if now > req.expires_at:
            audit = get_audit_logger()
            audit.record_event(
                event_type="CONFIRMATION_EXPIRED",
                action=req.action,
                risk_level=req.risk_level,
                status="EXPIRED",
                details={"token": clean_token},
            )
            return False, f"Confirmation request for '{req.action}' has expired."

        clean_resp = user_response.strip().lower()

        audit = get_audit_logger()
        if clean_resp in self.AFFIRMATIVE_GRAMMAR:
            audit.record_event(
                event_type="CONFIRMATION_APPROVED",
                action=req.action,
                risk_level=req.risk_level,
                status="APPROVED",
                details={"token": clean_token, "response": clean_resp},
            )
            return True, f"Approved action '{req.action}'."

        if clean_resp in self.NEGATIVE_GRAMMAR:
            audit.record_event(
                event_type="CONFIRMATION_DENIED",
                action=req.action,
                risk_level=req.risk_level,
                status="CANCELLED_BY_USER",
                details={"token": clean_token, "response": clean_resp},
            )
            return False, "Action cancelled by user."

        audit.record_event(
            event_type="CONFIRMATION_AMBIGUOUS",
            action=req.action,
            risk_level=req.risk_level,
            status="REJECTED_AMBIGUOUS",
            details={"token": clean_token, "response": clean_resp},
        )
        return False, "Unrecognized confirmation response. Action cancelled for safety."

    def invalidate_all(self, reason: str = "Kill switch activated") -> int:
        """Invalidate all pending tokens immediately."""
        count = len(self._pending_tokens)
        for req in self._pending_tokens.values():
            req.is_consumed = True

        self._pending_tokens.clear()
        audit = get_audit_logger()
        audit.record_event(
            event_type="CONFIRMATIONS_INVALIDATED",
            action="all",
            risk_level=3,
            status="INVALIDATED",
            details={"count": count, "reason": reason},
        )
        return count


_global_confirmation_manager: Optional[ConfirmationManager] = None


def get_confirmation_manager() -> ConfirmationManager:
    """Return confirmation manager singleton."""
    global _global_confirmation_manager
    if _global_confirmation_manager is None:
        _global_confirmation_manager = ConfirmationManager()
    return _global_confirmation_manager
