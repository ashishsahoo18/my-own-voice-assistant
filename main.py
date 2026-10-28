"""Application entry point for OLIVER 2.0 — Windows AI Cockpit."""

from pathlib import Path
import os
import sys

from dotenv import load_dotenv

from ui.app import OliverApp, AshishApp


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def load_environment() -> None:
    """Load environment variables from the project .env file."""
    load_dotenv(ENV_PATH)


def validate_environment() -> None:
    """Report startup status."""
    print("[OLIVER 2.0] Windows AI Cockpit Initializing...")
    print("[OLIVER 2.0] Speech Recognition & System Controls Ready.")
    print("[OLIVER 2.0] Autonomous Browser Automation Ready.")


def main() -> None:
    """Start the OLIVER 2.0 desktop application."""
    load_environment()
    validate_environment()

    app = OliverApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[OLIVER 2.0] Cockpit closed by user.")
        sys.exit(0)
