import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class AppSettings:
    """Central application settings loaded from environment variables."""

    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model = self._resolve_gemini_model()
        self.user_name = os.getenv("USER_NAME", "User").strip() or "User"
        self.voice_language = os.getenv("VOICE_LANGUAGE", "en").strip() or "en"
        self.theme = os.getenv("THEME", "dark").strip().lower() or "dark"

    def _resolve_gemini_model(self) -> str:
        configured = os.getenv("GEMINI_MODEL", "").strip()
        if configured.startswith("gemini-"):
            return configured
        return "gemini-1.5-flash"

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if value is None:
                continue
            setattr(self, key, value)
