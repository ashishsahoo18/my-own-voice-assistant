import os
import sys

from pathlib import Path

from dotenv import load_dotenv

from ui.app import AyraApp

load_dotenv(Path(__file__).resolve().parent / ".env")


def main() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        print("[Ayra] GEMINI_API_KEY is not set. Add it to the .env file to enable AI responses.")

    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
    if model_name:
        print(f"[Ayra] Using Gemini model: {model_name}")

    app = AyraApp()
    app.run()


if __name__ == "__main__":
    main()

