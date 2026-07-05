import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class AppSettings:
    """Central application settings loaded from environment variables."""

    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        self.user_name = os.getenv("USER_NAME", "User").strip() or "User"
        self.voice_language = os.getenv("VOICE_LANGUAGE", "en").strip() or "en"
        self.theme = os.getenv("THEME", "dark").strip().lower() or "dark"

    @property
    def is_gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if value is None:
                continue
            setattr(self, key, value)
