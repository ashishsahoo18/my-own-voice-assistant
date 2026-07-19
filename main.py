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
    """Show helpful startup warnings for missing optional settings."""
    if not os.getenv("GEMINI_API_KEY"):
        print(
            "[AYRA AI] GEMINI_API_KEY is not set. "
            "Add it to the .env file to enable AI responses."
        )

    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
    if model_name:
        print(f"[AYRA AI] Using Gemini model: {model_name}")


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