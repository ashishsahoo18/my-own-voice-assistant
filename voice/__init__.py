"""Voice subsystem package for OLIVER 2.0."""

from voice.audio_capture import AudioCapture, MicrophoneError
from voice.confirmation_bridge import VoiceConfirmationBridge
from voice.language import LanguageStatus, VoiceLanguage
from voice.listener import VoiceListener
from voice.speaker import VoiceSpeaker
from voice.states import VoiceState, VoiceStateMachine
from voice.stt import GoogleSTTEngine, LocalFirstSTTEngine, SpeechToTextEngine, TranscriptionResult, VoskSTTEngine
from voice.vad import VoiceActivityDetector
from voice.voice_manager import VoiceManager
from voice.wakeword import WakeWordDetector

__all__ = [
    "AudioCapture",
    "MicrophoneError",
    "VoiceConfirmationBridge",
    "LanguageStatus",
    "VoiceLanguage",
    "VoiceListener",
    "VoiceSpeaker",
    "VoiceState",
    "VoiceStateMachine",
    "SpeechToTextEngine",
    "TranscriptionResult",
    "VoskSTTEngine",
    "GoogleSTTEngine",
    "LocalFirstSTTEngine",
    "VoiceActivityDetector",
    "VoiceManager",
    "WakeWordDetector",
]
