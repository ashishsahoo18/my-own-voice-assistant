"""Application entry point for AYRA AI."""

from pathlib import Path
import os
import sys

from dotenv import load_dotenv

from ui.app import AyraApp


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def load_environment() -> None:
    """Load environment variables from the project .env file."""
    load_dotenv(ENV_PATH)


def validate_environment() -> None:
    """Report optional AI-provider status without blocking startup."""
    if os.getenv("GEMINI_API_KEY"):
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
        print(f"[AYRA AI] Optional Gemini provider enabled ({model_name}).")
    else:
        print("[AYRA AI] Starting with local commands and offline conversation support.")


def main() -> None:
    """Start the AYRA AI desktop application."""
    load_environment()
    validate_environment()

    app = AyraApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[AYRA AI] Closed by user.")
        sys.exit(0)
