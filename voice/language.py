"""Language mapping and validation status helpers for OLIVER 2.0 voice pipeline."""

from __future__ import annotations

from enum import Enum


class LanguageStatus(str, Enum):
    """Validation status for supported languages."""

    PRODUCTION = "PRODUCTION"                # Reliable local offline (Vosk) & external fallback
    MEASURED_EXTERNAL = "MEASURED_EXTERNAL"  # Measured capability via cloud fallback (Google STT)
    EXPERIMENTAL = "EXPERIMENTAL"            # Experimental / unvalidated


class VoiceLanguage:
    """Map supported languages to recognition codes, display labels, and validation tiers."""

    SUPPORTED = {
        "en": "en-US",
        "english": "en-US",
        "hi": "hi-IN",
        "hindi": "hi-IN",
        "or": "or-IN",
        "odia": "or-IN",
        "odisha": "or-IN",
    }

    LABELS = {
        "en": "English",
        "english": "English",
        "hi": "Hindi",
        "hindi": "Hindi",
        "or": "Odia (Experimental)",
        "odia": "Odia (Experimental)",
        "odisha": "Odia (Experimental)",
    }

    NORMALIZED_CODES = {
        "english": "en",
        "hindi": "hi",
        "odia": "or",
        "odisha": "or",
    }

    STATUS = {
        "en": LanguageStatus.PRODUCTION,
        "hi": LanguageStatus.MEASURED_EXTERNAL,
        "or": LanguageStatus.EXPERIMENTAL,
    }

    @classmethod
    def normalize(cls, code: str) -> str:
        """Return normalized language code."""
        clean_code = (code or "").strip().lower()
        return cls.NORMALIZED_CODES.get(clean_code, clean_code or "en")

    @classmethod
    def to_recognition_language(cls, code: str) -> str:
        """Return speech-recognition language code."""
        clean_code = cls.normalize(code)
        return cls.SUPPORTED.get(clean_code, "en-US")

    @classmethod
    def get_label(cls, code: str) -> str:
        """Return user-facing language label."""
        clean_code = cls.normalize(code)
        return cls.LABELS.get(clean_code, "English")

    @classmethod
    def get_status(cls, code: str) -> LanguageStatus:
        """Return the tested validation status of a language."""
        clean_code = cls.normalize(code)
        return cls.STATUS.get(clean_code, LanguageStatus.EXPERIMENTAL)

    @classmethod
    def is_experimental(cls, code: str) -> bool:
        """Return True if language recognition is experimental/unvalidated."""
        return cls.get_status(code) == LanguageStatus.EXPERIMENTAL

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """Return supported language choices with capability tier for settings UI."""
        return [
            ("en", "English"),
            ("hi", "Hindi"),
            ("or", "Odia (Experimental)"),
        ]