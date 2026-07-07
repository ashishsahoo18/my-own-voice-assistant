from __future__ import annotations


class VoiceLanguage:
    """Map supported languages to recognition and speech values."""

    SUPPORTED = {
        "en": "en-US",
        "hi": "hi-IN",
        "or": "or-IN",
    }

    @classmethod
    def to_recognition_language(cls, code: str) -> str:
        return cls.SUPPORTED.get(code.lower(), "en-US")

    @classmethod
    def get_label(cls, code: str) -> str:
        labels = {"en": "English", "hi": "Hindi", "or": "Odia"}
        return labels.get(code.lower(), "English")
