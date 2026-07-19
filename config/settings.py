"""Application configuration for AYRA AI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


@dataclass
class AppSettings:
    """Central application settings loaded from environment variables."""

    base_dir: Path = field(default_factory=lambda: BASE_DIR)
    env_path: Path = field(default_factory=lambda: ENV_PATH)

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "AYRA AI").strip())
    user_name: str = field(default_factory=lambda: os.getenv("USER_NAME", "Ashish").strip() or "User")

    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip())
    gemini_model: str = field(default_factory=lambda: AppSettings.resolve_gemini_model())

    voice_language: str = field(default_factory=lambda: os.getenv("VOICE_LANGUAGE", "en").strip() or "en")
    voice_rate: int = field(default_factory=lambda: AppSettings.resolve_int("VOICE_RATE", 175))
    voice_volume: float = field(default_factory=lambda: AppSettings.resolve_float("VOICE_VOLUME", 1.0))

    wake_word: str = field(default_factory=lambda: os.getenv("WAKE_WORD", "hey ayra").strip().lower())
    auto_send_voice: bool = field(default_factory=lambda: AppSettings.resolve_bool("AUTO_SEND_VOICE", False))
    auto_speaking: bool = field(default_factory=lambda: AppSettings.resolve_bool("AUTO_SPEAKING", True))

    theme: str = field(default_factory=lambda: os.getenv("THEME", "dark").strip().lower() or "dark")
    accent_color: str = field(default_factory=lambda: os.getenv("ACCENT_COLOR", "#1477ff").strip() or "#1477ff")

    database_path: Path = field(default_factory=lambda: BASE_DIR / "database" / "ayra.db")
    logs_dir: Path = field(default_factory=lambda: BASE_DIR / "logs")
    screenshots_dir: Path = field(default_factory=lambda: BASE_DIR / "screenshots")
    assets_dir: Path = field(default_factory=lambda: BASE_DIR / "assets")

    @property
    def is_gemini_configured(self) -> bool:
        """Return True when Gemini API key is available."""
        return bool(self.gemini_api_key)

    @staticmethod
    def resolve_gemini_model() -> str:
        """Resolve Gemini model from the environment with a safe default."""
        configured = os.getenv("GEMINI_MODEL", "").strip()

        if configured.startswith("gemini-"):
            return configured

        return "gemini-1.5-flash"

    @staticmethod
    def resolve_bool(key: str, default: bool) -> bool:
        """Read a boolean environment variable."""
        value = os.getenv(key)

        if value is None:
            return default

        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def resolve_int(key: str, default: int) -> int:
        """Read an integer environment variable."""
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default

    @staticmethod
    def resolve_float(key: str, default: float) -> float:
        """Read a float environment variable."""
        try:
            return float(os.getenv(key, str(default)))
        except ValueError:
            return default

    def ensure_directories(self) -> None:
        """Create runtime directories used by AYRA."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def update(self, **kwargs: object) -> None:
        """Update settings values at runtime."""
        for key, value in kwargs.items():
            if value is None:
                continue

            if not hasattr(self, key):
                raise AttributeError(f"Unknown setting: {key}")

            setattr(self, key, value)