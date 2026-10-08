"""Central typed configuration for OLIVER 2.0."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load project .env if it exists
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


class LLMSettings(BaseModel):
    """Local-first Ollama and model configuration."""

    provider: str = Field(default="ollama", description="Default LLM provider")
    ollama_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
    )
    model: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.2").strip()
    )
    vision_model: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_VISION_MODEL", "llava").strip()
    )
    timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT", "120").strip())
    )
    max_retries: int = Field(default=2, ge=0, le=5)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class VoiceSettings(BaseModel):
    """Speech recognition and synthesis configuration."""

    engine: str = Field(
        default_factory=lambda: os.getenv("VOICE_ENGINE", "legacy").strip().lower()
    )
    language: str = Field(
        default_factory=lambda: os.getenv("VOICE_LANGUAGE", "en").strip().lower()
    )
    rate: int = Field(
        default_factory=lambda: int(os.getenv("VOICE_RATE", "175").strip())
    )
    volume: float = Field(
        default_factory=lambda: float(os.getenv("VOICE_VOLUME", "1.0").strip())
    )
    voice_id: Optional[str] = Field(
        default_factory=lambda: os.getenv("VOICE_ID", "").strip() or None
    )
    wake_word: str = Field(
        default_factory=lambda: os.getenv("WAKE_WORD", "hey oliver").strip().lower()
    )
    wake_word_alias: str = Field(
        default_factory=lambda: os.getenv("WAKE_WORD_ALIAS", "hey ashish").strip().lower()
    )
    auto_speaking: bool = Field(
        default_factory=lambda: os.getenv("AUTO_SPEAKING", "true").strip().lower() in {"1", "true", "yes", "on"}
    )
    auto_send_voice: bool = Field(
        default_factory=lambda: os.getenv("AUTO_SEND_VOICE", "false").strip().lower() in {"1", "true", "yes", "on"}
    )


class SecuritySettings(BaseModel):
    """Safety and sandboxing policy configuration."""

    enabled: bool = Field(default=True)
    allow_arbitrary_commands: bool = Field(
        default=False,
        description="Arbitrary shell execution is disabled by default for security."
    )
    allowlist_roots: list[Path] = Field(
        default_factory=lambda: [
            BASE_DIR,
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path.home() / "Downloads",
            Path.home() / "Pictures",
            Path.home() / "Videos",
        ]
    )
    max_plan_steps: int = Field(default=6, ge=1, le=10)
    recycle_bin_deletes: bool = Field(default=True)
    confirmation_timeout_seconds: float = Field(default=30.0)


class StorageSettings(BaseModel):
    """Storage, database, and logging directories."""

    base_dir: Path = Field(default_factory=lambda: BASE_DIR)
    database_dir: Path = Field(default_factory=lambda: BASE_DIR / "database")
    database_path: Path = Field(default_factory=lambda: BASE_DIR / "database" / "oliver.db")
    logs_dir: Path = Field(default_factory=lambda: BASE_DIR / "logs")
    backups_dir: Path = Field(default_factory=lambda: BASE_DIR / "backups")
    screenshots_dir: Path = Field(default_factory=lambda: BASE_DIR / "screenshots")
    contacts_path: Path = Field(default_factory=lambda: BASE_DIR / "contacts.csv")

    def ensure_directories(self) -> None:
        """Create storage directories if they do not exist."""
        self.database_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)


class OliverConfig(BaseModel):
    """Master application configuration for OLIVER 2.0."""

    app_name: str = Field(
        default_factory=lambda: os.getenv("APP_NAME", "OLIVER").strip()
    )
    version: str = Field(default="2.0.0")
    user_name: str = Field(
        default_factory=lambda: os.getenv("USER_NAME", "Ashish").strip() or "User"
    )
    theme: str = Field(
        default_factory=lambda: os.getenv("THEME", "dark").strip().lower()
    )
    accent_color: str = Field(
        default_factory=lambda: os.getenv("ACCENT_COLOR", "#00d2ff").strip()
    )

    router_mode: str = Field(
        default_factory=lambda: os.getenv("ROUTER_MODE", "legacy").strip().lower(),
        description="Feature flag: 'legacy' uses original dispatch; 'oliver' uses skill registry."
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)

    def is_path_allowed(self, target: Path | str) -> bool:
        """Check if target path is inside allowed root folders."""
        try:
            resolved = Path(target).resolve()
            for allowed in self.security.allowlist_roots:
                allowed_resolved = allowed.resolve()
                if resolved == allowed_resolved or allowed_resolved in resolved.parents:
                    return True
            return False
        except Exception:
            return False


@lru_cache(maxsize=1)
def get_config() -> OliverConfig:
    """Return cached singleton configuration instance."""
    config = OliverConfig()
    config.storage.ensure_directories()
    return config


def reload_config() -> OliverConfig:
    """Reload configuration and invalidate cache."""
    get_config.cache_clear()
    return get_config()
