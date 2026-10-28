# Dependencies Inventory & Justification — OLIVER 2.0

## Phase 1 Dependency Status

No new external packages were required or installed for Phase 1. All Phase 1 modules (`core/config.py`, `core/logging.py`, `core/errors.py`) rely exclusively on Python standard library modules and existing environment packages (`pydantic` and `python-dotenv`).

## Current Environment Dependencies

| Package | Version | Purpose | Justification |
|---|---|---|---|
| `customtkinter` | 6.0.0 | Desktop GUI framework | Powers the dark-mode HUD Cockpit and Canvas Orb |
| `Pillow` | 12.0.0 | Image processing | Asset and icon handling in CustomTkinter |
| `python-dotenv` | 1.2.2 | Environment variable loading | Loads `.env` configuration securely |
| `pydantic` | 2.12.5 | Data validation & schemas | Powers `core/config.py` typed configuration |
| `requests` | 2.32.5 | HTTP client | Communicates with local Ollama REST endpoints |
| `SpeechRecognition`| 3.14.4 | Audio capture | Voice input listener (legacy) |
| `pyttsx3` | 2.98 | Local Text-to-Speech | 100% offline Windows SAPI5 voice output |
| `psutil` | 7.2.2 | System monitoring | Live CPU, RAM, and Battery telemetry |
| `pyautogui` | 0.9.54 | UI automation & screenshots | Desktop screenshot capture |
| `pyperclip` | 1.11.0 | Clipboard operations | Copy and paste commands |
| `pywin32` | 310 | Win32 API integration | Low-level Windows desktop automation |
| `PyGetWindow` | 0.0.9 | Window management | Windows desktop automation |
| `google-generativeai` | 0.8.6 | Legacy cloud client | Legacy compatibility shim (unused by default) |
| `pyaudio` | 0.2.14 | Low-level microphone capture | Required by SpeechRecognition on Windows |
| `sqlite3` | Built-in | Relational database storage | Offline chat, reminder, and memory storage |

## Security & License Audit
- All packages are compatible with MIT / Apache 2.0 / BSD open-source licensing.
- Zero paid API packages are mandatory; local Ollama + Llama 3.2 is the primary AI engine.
