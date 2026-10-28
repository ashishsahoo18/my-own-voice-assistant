"""Action-bound voice confirmation bridge for sensitive/dangerous actions in OLIVER 2.0."""

from __future__ import annotations

import logging
from typing import Optional

from core.logging import get_audit_logger
from security.confirmation import ConfirmationManager, ConfirmationRequest, get_confirmation_manager


class VoiceConfirmationBridge:
    """Safely resolves action-bound confirmations using voice recognition without bypassing security policies."""

    def __init__(
        self,
        confirmation_manager: Optional[ConfirmationManager] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.confirmation_manager = confirmation_manager or get_confirmation_manager()
        self.logger = logger or logging.getLogger(__name__)

    def process_voice_response(self, token: str, spoken_transcript: str) -> tuple[bool, str]:
        """Verify action-bound token against spoken transcript.
        
        Strictly rejects ambiguous, uncertain, or unrelated speech.
        Single-use tokens cannot be reused.
        """
        clean_text = (spoken_transcript or "").strip()
        self.logger.info("Processing voice confirmation for token %s: '%s'", token, clean_text)

        audit = get_audit_logger()
        audit.record_event(
            event_type="VOICE_CONFIRMATION_ATTEMPT",
            action="voice.verify_confirmation",
            risk_level=2,
            status="EVALUATING",
            details={"token": token, "transcript": clean_text},
        )

        if not clean_text:
            # Empty recognition / silence / unintelligible speech
            is_approved, msg = self.confirmation_manager.verify_and_consume(token, "")
            self.logger.warning("Voice confirmation aborted due to empty/unintelligible speech: %s", msg)
            return False, f"Speech not recognized. {msg}"

        # Delegate to ConfirmationManager grammar enforcement
        is_approved, explanation = self.confirmation_manager.verify_and_consume(token, clean_text)

        if is_approved:
            self.logger.info("Voice confirmation approved for token %s", token)
        else:
            self.logger.warning("Voice confirmation rejected/denied for token %s: %s", token, explanation)

        return is_approved, explanation
