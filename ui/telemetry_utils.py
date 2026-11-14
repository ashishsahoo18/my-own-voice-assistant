"""Telemetry formatting and helper utilities for OLIVER 3.0 Cockpit UI (Stage 2B)."""

from __future__ import annotations

import math
from typing import Any, Optional


def format_confidence(
    confidence: Any,
    available: bool = True,
    text: Optional[str] = None,
) -> str:
    """Format confidence score into human-readable string.

    Rules:
    - Direct TranscriptionResult support: introspects confidence, available, and text.
    - If text is provided and empty (silence/timeout/empty utterance), returns 'N/A'.
    - If available is False or confidence is None, returns 'N/A'.
    - Rejects booleans (True/False are not numbers), returns 'N/A'.
    - Rejects NaN, Inf, negative, and values > 1.0, returns 'N/A'.
    - Valid confidence >= 0.25 returns '{pct}%'.
    - Valid confidence < 0.25 returns '{pct}% — Low confidence'.
    """
    if hasattr(confidence, "confidence") and hasattr(confidence, "text"):
        text = getattr(confidence, "text", text)
        available = getattr(confidence, "confidence_available", available)
        confidence = getattr(confidence, "confidence", None)

    # Stage 2E Condition 2: Empty utterance (silence/timeout) displays 'N/A'
    if text is not None and not str(text).strip():
        return "N/A"

    if not available or confidence is None or isinstance(confidence, bool):
        return "N/A"

    if not isinstance(confidence, (int, float)):
        return "N/A"

    try:
        conf_float = float(confidence)
        if math.isnan(conf_float) or math.isinf(conf_float) or conf_float < 0.0 or conf_float > 1.0:
            return "N/A"

        pct = round(conf_float * 100)
        if conf_float < 0.25:
            return f"{pct}% — Low confidence"
        return f"{pct}%"
    except (ValueError, TypeError):
        return "N/A"


def format_stt_latency(latency_s: Any) -> str:
    """Format STT latency duration in milliseconds.

    Rules:
    - If latency_s is None, bool, non-numeric, or <= 0.0, returns 'N/A'.
    - Rejects NaN, Inf, returns 'N/A'.
    - Valid positive float duration is converted to round milliseconds ('{ms} ms').
    """
    if latency_s is None or isinstance(latency_s, bool):
        return "N/A"

    try:
        lat_float = float(latency_s)
        if math.isnan(lat_float) or math.isinf(lat_float) or lat_float <= 0.0:
            return "N/A"

        ms = round(lat_float * 1000)
        return f"{ms} ms"
    except (ValueError, TypeError):
        return "N/A"


def format_stt_engine(engine_name: Optional[str]) -> str:
    """Format active STT engine identifier into display title."""
    if not engine_name or not isinstance(engine_name, str):
        return "Vosk"

    clean = engine_name.strip().lower()
    if clean in ("vosk", "local_first_hybrid", "offline"):
        return "Vosk"
    if clean == "google":
        return "Google STT"
    return engine_name.strip().capitalize()


def get_status_color(status: str) -> str:
    """Return appropriate hex text color for a given voice state."""
    clean = (status or "").upper().replace("STATUS:", "").strip()
    if "READY" in clean:
        return "#00ff9d"  # Mint green
    if "LISTENING" in clean:
        return "#00d2ff"  # Electric cyan
    if "PROCESSING" in clean:
        return "#ffcf36"  # Amber yellow
    if "SPEAKING" in clean:
        return "#36b6ff"  # Soft blue
    if "ERROR" in clean:
        return "#ff4444"  # Alert red
    if "DISABLED" in clean or "UNAVAILABLE" in clean:
        return "#64748b"  # Slate gray
    return "#cbd5e1"      # Default light slate


def get_confidence_color(
    confidence: Any,
    available: bool = True,
    text: Optional[str] = None,
) -> str:
    """Return appropriate hex text color for a confidence score."""
    if hasattr(confidence, "confidence") and hasattr(confidence, "text"):
        text = getattr(confidence, "text", text)
        available = getattr(confidence, "confidence_available", available)
        confidence = getattr(confidence, "confidence", None)

    # Stage 2E Condition 2: Empty utterance returns neutral slate
    if text is not None and not str(text).strip():
        return "#8899ac"

    if not available or confidence is None or isinstance(confidence, bool):
        return "#8899ac"

    try:
        conf_float = float(confidence)
        if math.isnan(conf_float) or math.isinf(conf_float) or conf_float < 0.0 or conf_float > 1.0:
            return "#8899ac"
        if conf_float < 0.25:
            return "#ff4444"  # Warning red for low confidence
        if conf_float >= 0.70:
            return "#00ff9d"  # High confidence green
        return "#00d2ff"      # Moderate confidence cyan
    except (ValueError, TypeError):
        return "#8899ac"
