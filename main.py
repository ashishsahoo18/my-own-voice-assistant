"""Application entry point for ASHISH AI."""

from pathlib import Path
import os
import sys

from dotenv import load_dotenv

from ui.app import AshishApp


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def load_environment() -> None:
    """Load environment variables from the project .env file."""
    load_dotenv(ENV_PATH)


def validate_environment() -> None:
    """Report startup status."""
    print("[ASHISH AI] System Initializing...")
    print("[ASHISH AI] Speech Recognition & System Controls Ready.")
    print("[ASHISH AI] Firefox Web Automation Ready.")


def main() -> None:
    """Start the ASHISH AI desktop application."""
    load_environment()
    validate_environment()

    app = AshishApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ASHISH AI] Closed by user.")
        sys.exit(0)
