"""Base abstract interfaces for Speech-to-Text (STT) engines in OLIVER 2.0."""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import speech_recognition as sr


@dataclass
class TranscriptionResult:
    """Standardized speech recognition transcription output."""

    text: str
    confidence: Optional[float] = None
    engine: str = "unknown"
    is_offline: bool = True
    latency_s: float = 0.0
    external_service_disclosed: bool = False
    confidence_available: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Sanitize and validate confidence score."""
        if not self.confidence_available or self.confidence is None or isinstance(self.confidence, bool):
            self.confidence = None
            self.confidence_available = False
            return

        try:
            import math
            conf = float(self.confidence)
            if math.isnan(conf) or math.isinf(conf) or conf < 0.0 or conf > 1.0:
                self.confidence = None
                self.confidence_available = False
            else:
                self.confidence = conf
                self.confidence_available = True
        except (ValueError, TypeError):
            self.confidence = None
            self.confidence_available = False

    @property
    def is_empty(self) -> bool:
        """Return True if transcription produced no text."""
        return not bool(self.text and self.text.strip())


class SpeechToTextEngine(abc.ABC):
    """Abstract base class for all STT providers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name identifier of the engine."""

    @property
    @abc.abstractmethod
    def is_offline(self) -> bool:
        """Whether this engine runs completely offline on the local machine."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if dependencies and models required by this engine are available."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio_data: sr.AudioData,
        language: str = "en",
    ) -> TranscriptionResult:
        """Transcribe audio into text."""
