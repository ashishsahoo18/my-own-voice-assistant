import os
import sys

from pathlib import Path

from dotenv import load_dotenv

from ui.app import AyraApp

load_dotenv(Path(__file__).resolve().parent / ".env")


def main() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        print("[Ayra] GEMINI_API_KEY is not set. Add it to the .env file to enable AI responses.")

    app = AyraApp()
    app.run()


if __name__ == "__main__":
    main()

