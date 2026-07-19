"""Language mapping helpers for AYRA AI voice features."""

from __future__ import annotations


class VoiceLanguage:
    """Map supported languages to recognition and display values."""

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
        "or": "Odia",
        "odia": "Odia",
        "odisha": "Odia",
    }

    NORMALIZED_CODES = {
        "english": "en",
        "hindi": "hi",
        "odia": "or",
        "odisha": "or",
    }

    @classmethod
    def normalize(cls, code: str) -> str:
        """Return normalized language code."""
        clean_code = code.strip().lower()
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
    def choices(cls) -> list[tuple[str, str]]:
        """Return supported language choices for settings UI."""
        return [
            ("en", "English"),
            ("hi", "Hindi"),
            ("or", "Odia"),
        ]