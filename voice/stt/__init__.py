"""Speech-to-Text package for OLIVER 2.0."""

from voice.stt.base import SpeechToTextEngine, TranscriptionResult
from voice.stt.google_engine import GoogleSTTEngine
from voice.stt.local_first import LocalFirstSTTEngine
from voice.stt.vosk_engine import VoskSTTEngine

__all__ = [
    "SpeechToTextEngine",
    "TranscriptionResult",
    "VoskSTTEngine",
    "GoogleSTTEngine",
    "LocalFirstSTTEngine",
]
