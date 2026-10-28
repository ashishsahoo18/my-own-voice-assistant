# OLIVER 2.0: Comprehensive Project Audit (Phase 0)

**Date:** October 8, 2026  
**Auditor:** Senior AI Architect & System Engineer (Antigravity)  
**Target Assistant:** OLIVER 2.0  
**Current System:** ASHISH AI / AYRA AI  
**Repository Working Directory:** `c:\Users\ASHISH\OneDrive\Desktop\Documents\my own voice assistant`  
**Git Branch / Commit:** `main` (clean working tree at `dbd4dac`)  

---

## 1. Executive Summary

This Phase 0 read-only audit examines the existing Windows voice assistant codebase to prepare for an incremental upgrade to **OLIVER 2.0**. No existing files were deleted, moved, modified, or reformatted during this audit.

### Key Discoveries:
1. **Dual Brand Identity**: The codebase currently exhibits a hybrid identity. It was originally engineered under the name **AYRA AI** (visible across database names `ayra_chat.db`, `ayra_memory.db`, loggers `ayra.*`, settings defaults, and folder `ayra_workspace`), and partially rebranded to **ASHISH AI** (in `main.py`, `README.md`, `.env`, `ui/app.py`, `ui/chat.py`, `tests/test_assistant_upgrade.py`). The name **OLIVER** does not appear anywhere in the existing codebase.
2. **Local AI Foundation**: The project has already migrated its primary LLM backend from Google Gemini to local **Ollama + Llama 3.2** via `ai/ai_service.py` with endpoint auto-probing (`localhost:11434`, `127.0.0.1:11434`), tag resolution, and offline fallback. Ollama is currently online and running `llama3.2:latest` on this machine.
3. **Automated Baseline Verification**: The existing automated test suite (`tests/test_assistant_upgrade.py` and `tests/test_gemini_client.py`) contains **19 unit tests**, all of which **PASS** (19/19 in 0.205s) when executed with mocked external dependencies.
4. **Data Fragmentation**: User data is scattered across three separate SQLite databases (`database/ayra_chat.db`, `database/ayra_memory.db`, `database/memory.db`), one CSV file (`contacts.csv`), and one JSON configuration (`config/voice_settings.json`).
5. **Git Hygiene & Leaks**: Git tracks active runtime artifacts: log files (`logs/automation.log`, `logs/database.log`, `logs/voice.log`), SQLite databases (`database/*.db`), personal contacts (`contacts.csv`), and screenshots (`screenshots/screenshot.png`). `.gitignore` only ignores `.env`, `venv`, `__pycache__`, and `.vscode`.
6. **Voice Pipeline Cloud Dependency**: While TTS (`pyttsx3`) is 100% offline and local, STT (`voice/listener.py`) and wake-word detection (`voice/wakeword.py`) depend on `recognize_google` (Google's public cloud Speech Recognition API). The background wake word detector polls Google Cloud STT every 1–2 seconds.
7. **Security Vulnerabilities**:
   - Arbitrary `eval()` used in `commands/productivity.py` and `commands/system.py` for mathematical calculation.
   - `shell=True` used in `commands/system.py` for Windows target launch fallbacks and command execution.
   - No path traversal sanitization in file operations (`commands/files.py`).
   - WhatsApp message automation relies on UI automation (`pyautogui.press("enter")`) after a fixed 4-second delay without verifying message dispatch or delivery.

---

## 2. Codebase Inventory & Directory Structure

```
my own voice assistant/
├── .env                         <- Local runtime environment variables
├── .env.example                 <- Environment template
├── .git/                        <- Git repository (on main)
├── .gitignore                   <- Basic ignore file (incomplete: logs & db tracked)
├── LICENSE                      <- Project license file
├── README.md                    <- 673-line technical documentation for ASHISH AI
├── requirements.txt             <- Dependencies (11 packages listed)
├── main.py                      <- Application entry point (AshishApp)
├── contacts.csv                 <- Local address book (4 contacts: Maa, Deba, Rahul x2)
│
├── ai/                          <- Intelligence & AI client layer
│   ├── __init__.py
│   ├── ai_service.py            <- Ollama REST client (llama3.2, /api/chat, /api/generate)
│   ├── assistant.py             <- Monolithic brain (AshishAssistant) & regex intent router
│   ├── gemini_client.py         <- Backward compatibility adapter wrapping AIService
│   ├── gemini_client.py.bak     <- Backup file
│   ├── memory.py                <- In-memory short-term ConversationMemory (sliding window)
│   ├── memory_manager.py        <- Long-term MemoryManager for SQLite memory.db
│   ├── memory_prompt.py         <- MemoryPromptBuilder for context injection
│   └── openaiclient.py          <- Legacy OpenAI client stub (unused)
│
├── assets/                      <- UI graphic assets
│   ├── avatar.png               <- Assistant orb/avatar image
│   ├── icon.ico                 <- Window icon
│   └── icons/                   <- Subdirectory for icon assets
│
├── ayra_workspace/              <- Empty workspace directory (legacy Ayra artifact)
├── captures/                    <- Empty captures directory
├── screenshots/                 <- Screenshot capture directory (contains screenshot.png)
├── logs/                        <- Log directory (currently tracked in git)
│   ├── automation.log
│   ├── ayra.log
│   ├── database.log
│   └── voice.log
│
├── commands/                    <- Automation command modules
│   ├── __init__.py
│   ├── browser.py               <- Browser opening & search (27 site mappings)
│   ├── calculator.py            <- Regex-based safe math evaluator
│   ├── clipboard.py             <- Pyperclip clipboard copy/paste/view
│   ├── contacts.py              <- ContactManager with ambiguity resolution
│   ├── email_service.py         <- Gmail SMTP sender & browser mailto/web compose fallback
│   ├── files.py                 <- File & folder CRUD, rename, move, copy
│   ├── news.py                  <- NewsData.io API headlines integration
│   ├── productivity.py          <- Stopwatch, countdown thread, pomodoro/note stubs, eval()
│   ├── reminders.py             <- SQLite-backed reminders (ayra_memory.db)
│   ├── router.py                <- CommandRouter (keyword/regex dispatch to commands)
│   ├── screenshot.py            <- PyAutoGUI screen capture
│   ├── system.py                <- OS volume (nircmd), power, apps, eval(), shell=True
│   ├── weather.py               <- Open-Meteo REST API forecast integration
│   ├── whatsapp.py              <- WhatsApp Web automation via URL & pyautogui
│   ├── windows.py               <- Windows app launcher, workstation lock, explorer restart
│   └── youtube.py               <- YouTube video ID resolution, search, and playback
│
├── config/                      <- Configuration layer
│   ├── __init__.py
│   ├── personality.py           <- Prompt engineering & assistant personality templates
│   ├── settings.py              <- AppSettings dataclass loading .env
│   └── voice_settings.json      <- Persisted voice engine configuration (rate, vol, voice_id)
│
├── database/                    <- Persistence layer (3 SQLite DBs + access classes)
│   ├── ayra_chat.db             <- ChatStore database (chat_sessions, chat_messages)
│   ├── ayra_memory.db           <- ReminderCommands database (reminders)
│   ├── memory.db                <- AyraDatabase (users, chats, messages, memory, settings, notes)
│   ├── chat_db.py               <- ChatStore SQLite helper
│   ├── database.py              <- AyraDatabase SQLite helper
│   └── models.py                <- Dataclasses: UserProfile, MemoryItem, Reminder, Note
│
├── ui/                          <- Graphical User Interface (CustomTkinter)
│   ├── __init__.py
│   ├── app.py                   <- AshishApp 3-column cockpit window + ConfirmationModal
│   ├── chat.py                  <- CommandConsolePanel, CommandConsoleEntry, transcript feed
│   └── setting.py               <- VoiceSettingsWindow toplevel dialog
│
├── voice/                       <- Audio & Speech layer
│   ├── __init__.py
│   ├── language.py              <- VoiceLanguage normalizer (en-US, hi-IN, or-IN)
│   ├── listener.py              <- VoiceListener (SpeechRecognition + recognize_google)
│   ├── speaker.py               <- VoiceSpeaker (pyttsx3 SAPI5 local TTS)
│   ├── voice_manager.py         <- VoiceManager coordinator
│   └── wakeword.py              <- WakeWordDetector (background thread + recognize_google)
│
├── scratch/                     <- Scratchpad scripts (experimental tests)
│   ├── check_ollama.py
│   ├── live_search_demo.py
│   ├── test_pipeline.py
│   ├── test_play.py
│   ├── test_selenium.py
│   ├── test_yt.py
│   ├── test_yt_commands.py
│   └── verify_imports.py
│
└── tests/                       <- Test suite
    ├── run_local_checks.py      <- Ad-hoc desktop test script (side-effecting)
    ├── test_assistant_upgrade.py<- 12 unit tests for AshishAssistant
    └── test_gemini_client.py    <- 7 unit tests for AIService / Ollama health checks
```

---

## 3. Detailed Component Analysis

### 3.1 Entry Point & Startup Flow
- **`main.py`**:
  1. Loads `.env` via `python-dotenv`.
  2. Prints initialization messages (`[ASHISH AI] System Initializing...`).
  3. Instantiates `ui.app.AshishApp()`.
  4. Starts CustomTkinter GUI mainloop via `app.run()` (`self.mainloop()`).
- **`ui/app.py` Startup Cascade**:
  - Initializes `AppSettings()`.
  - Initializes `AshishAssistant()`.
  - Initializes `ChatStore()`.
  - Initializes `VoiceManager()`.
  - Builds 3-column layout:
    - Left: System Monitor (CPU, RAM, Battery, Network status via `psutil`).
    - Center: CustomTkinter Canvas Animated Orb (multi-ring rotating arcs, pulsing radius).
    - Right: `CommandConsolePanel` (Quick command buttons, speech transcript box, event log feed).
  - Starts background hardware polling timer (`self.after(2000, self._update_system_stats)`).
  - Starts Canvas orb animation timer (`self.after(35, self._animate_orb)`).
  - Spawns background wake-word listener thread via `voice_manager.wake_detector.start()`.

### 3.2 Dispatch & Intent Routing
- **Dual Routing Architecture**:
  - `ai/assistant.py` (`AshishAssistant.handle`) inspects message text using keyword matching (`determine_intent`) and intercepts dangerous commands (`is_dangerous_command`).
  - It then calls `commands/router.py` (`CommandRouter.route`), which executes a secondary regex/keyword matching pipeline across 9 categories.
  - If no automation matches, control returns to `AshishAssistant`, which tries memory commands, and finally falls back to `ai_service.ask(text)`.
- **Strengths**: Deterministic routing ensures system commands, app launches, and searches do not rely on flaky LLM tool-calling.
- **Weaknesses**: Code duplication between `AshishAssistant` and `CommandRouter`; rigid regexes break on slight phrasing variations; no central policy enforcement layer; confirmation strings are parsed from raw return string prefixes (`"CONFIRMATION_REQUIRED:..."`).

### 3.3 LLM & Local AI Integration
- **`ai/ai_service.py`**:
  - Connects to Ollama REST API (`/api/chat` with fallback to `/api/generate`).
  - Probes endpoints dynamically: configured `OLLAMA_URL`, `http://127.0.0.1:11434`, `http://localhost:11434`.
  - Probes `/api/tags` to discover available models.
  - Matches `OLLAMA_MODEL` (default: `llama3.2`) or auto-selects first installed model if tag differs (e.g., `llama3.2:latest`).
  - Graceful degradation: returns clear user message (`"Local AI is offline. Please start Ollama."` or `"No local AI model is installed..."`) without raising uncaught exceptions.
  - Tested: verified Ollama is currently online and running `llama3.2:latest` on this machine.
- **`ai/gemini_client.py`**: Legacy shim forwarding all calls to `AIService`. `gemini_api_key` is unused.

### 3.4 Speech & Voice Processing
- **Text-to-Speech (TTS)**:
  - `voice/speaker.py`: Built on `pyttsx3` using Windows SAPI5.
  - Local, offline, zero cloud dependency.
  - Text sanitizer (`_clean_text_for_speech`) strips markdown, code blocks, URLs, and backticks.
  - Thread-safe with `threading.RLock()`.
- **Speech-to-Text (STT)**:
  - `voice/listener.py`: Uses `SpeechRecognition` library.
  - Calls `recognizer.recognize_google(audio, language=self.language)`.
  - **Dependency**: Requires internet access to reach Google's speech recognition web API.
  - Languages supported by Google STT wrapper: `en-US`, `hi-IN`, `or-IN`.
- **Wake Word**:
  - `voice/wakeword.py`: Dedicated background thread executing a continuous listening loop.
  - Captures 1–2 second audio slices and repeatedly calls `recognize_google()`.
  - Inefficient and fragile: generates high network traffic and latency; fails completely when offline.

### 3.5 Persistence & Data Inventory
- Data is stored across multiple independent targets:
  1. `database/ayra_chat.db` (SQLite):
     - `chat_sessions`: session titles, timestamps.
     - `chat_messages`: roles (`user`, `assistant`), message content, session FK.
     - Current state: 1 session, 8 messages.
  2. `database/ayra_memory.db` (SQLite):
     - `reminders`: title, `remind_at`, `created_at`, `completed`.
     - Current state: 0 reminders.
  3. `database/memory.db` (SQLite):
     - `users`, `chats`, `messages`, `memory`, `settings`, `reminders`, `notes`.
     - Current state: 0 rows across all tables (schema initialized).
  4. `contacts.csv`:
     - Schema: `name,number,email`.
     - Current state: 4 contacts (contains personal contact entries).
  5. `config/voice_settings.json`:
     - Keys: `language`, `voice_id`, `speech_rate`, `volume`, `wake_word`, `auto_speaking`, `auto_send_voice`.
  6. `screenshots/`:
     - Saved screenshot PNG files.

---

## 4. Existing Features Inventory & Operational Status

| Category | Feature / Trigger | File & Function | Current Verification | Status |
|---|---|---|---|---|
| **App Launching** | "Open Notepad", "Launch VS Code", "Start Chrome", etc. (30+ apps) | `commands/windows.py` (`open_app`) & `commands/system.py` (`_launch_target`) | None (assumes process launched; no PID check) | **Works** |
| **Windows Controls** | "Lock computer" | `commands/windows.py` (`lock_computer`) | Calls Win32 `LockWorkStation` | **Works** |
| **Windows Controls** | "Restart explorer" | `commands/windows.py` (`restart_explorer`) | Runs `taskkill` + `explorer.exe` | **Works** |
| **System Audio** | "Volume up", "Volume down", "Mute" | `commands/system.py` (`volume_up`, `volume_down`, `mute`) | `nircmd.exe` (fails if binary missing) | **Flaky / External Dep** |
| **Power Actions** | "Shutdown", "Restart", "Sleep", "Log out" | `commands/system.py` / `commands/windows.py` | String confirmation trigger in UI modal | **Works** (Gated) |
| **Web Navigation** | "Open Google", "Open YouTube", "Open GitHub", etc. (27 sites) | `commands/browser.py` (`open_site`, `open_url`) | `webbrowser.open()` return value | **Works** |
| **Web Search** | "Search [query]", "Search Google for [query]" | `commands/browser.py` (`search_google`) | Opens Firefox / default browser | **Works** |
| **YouTube Play** | "Play [song/query]" | `commands/youtube.py` (`play_youtube`) | Scrapes video ID, opens URL, presses space | **Works** (Heuristic) |
| **YouTube Search**| "Search YouTube for [query]" | `commands/youtube.py` (`search_youtube`) | Opens YouTube search results URL | **Works** |
| **Files & Folders**| "Create folder [name]", "Create file [name]" | `commands/files.py` (`create_folder`, `create_file`) | Checks `exists()` locally | **Works** |
| **Files & Folders**| "Delete folder", "Delete file" | `commands/files.py` (`delete_folder`, `delete_file`) | Hardcoded refusal / stub redirect | **Incomplete** |
| **Files & Folders**| "List files in [path]", "Rename", "Move", "Copy" | `commands/files.py` | Direct `shutil`/`Path` operations | **Works** |
| **WhatsApp** | "Send WhatsApp message to [contact] saying [text]" | `commands/whatsapp.py` (`prepare_whatsapp_command`, `send_message`) | UI modal confirmation; opens URL + presses Enter | **Flaky** (Unverified delivery) |
| **Email / Gmail** | "Send email to [contact] saying [text]" | `commands/email_service.py` (`send_email`) | SMTP if credentials set; web compose fallback | **Works** (Fallback) |
| **Contacts** | "Contact ambiguity check" | `commands/contacts.py` (`resolve_contact`) | Ambiguity detection with matching list | **Works** |
| **Weather** | "Weather in [location]" | `commands/weather.py` (`get_weather`) | Open-Meteo REST API | **Works** |
| **News** | "News technology", "Latest news" | `commands/news.py` (`get_news`) | NewsData.io API (requires key) | **Degrades Gracefully** |
| **Screenshots** | "Take screenshot" | `commands/screenshot.py` (`take_screenshot`) | PyAutoGUI screenshot saved to disk | **Works** |
| **Clipboard** | "Copy [text]", "Paste", "Clear clipboard" | `commands/clipboard.py` | Pyperclip clipboard access | **Works** |
| **Calculator** | "Calculate [expression]" | `commands/system.py`, `commands/productivity.py` | Python `eval()` (unsafe!) | **Security Risk** |
| **Reminders** | "Remind me to [title]", "Show reminders" | `commands/reminders.py` | SQLite `ayra_memory.db` | **Works** |
| **Productivity** | "Start stopwatch", "Start countdown" | `commands/productivity.py` | In-memory timestamps & threads | **Works** |
| **Productivity** | "Pomodoro", "Daily planner", "Quick note" | `commands/productivity.py` | Returns static strings without saving | **Stub / Incomplete** |
| **Local AI Q&A** | "What is [concept]?", "Explain [topic]" | `ai/ai_service.py` (`ask`) | Ollama REST endpoint (`llama3.2`) | **Works** |
| **HUD Cockpit** | GUI with 3 panels, animated Canvas Orb, system telemetry | `ui/app.py`, `ui/chat.py` | Real-time Tkinter event loop | **Works** |
| **Voice Loop** | Speech recognition + TTS | `voice/listener.py`, `voice/speaker.py` | Google Cloud STT + Windows SAPI5 | **Works** (Online only) |

---

## 5. Security & Reliability Audit

### 5.1 Security Findings
1. **Arbitrary Code Execution via `eval()`**:
   - `commands/system.py:196`: `eval(expression, {"__builtins__": {}}, {})`
   - `commands/productivity.py:18`: `eval(expression, {"__builtins__": {}}, {})`
   - **Risk**: Python's restricted `eval()` with empty builtins is notoriously bypassable via attribute traversals (e.g. `().__class__.__base__.__subclasses__()`). Must be replaced with AST-based arithmetic parsing (`ast.literal_eval` or a deterministic expression tokenizer).
2. **Subprocess Invocations with `shell=True`**:
   - `commands/system.py:324`: `subprocess.Popen(f'start "" "{target}"', shell=True)`
   - `commands/system.py:337`: `subprocess.run(command, shell=True, check=False)`
   - **Risk**: Shell injection if user input reaches target execution. Must enforce argument lists (`shell=False`).
3. **Unchecked Path Operations**:
   - `commands/files.py`: Resolves paths without sandboxing to allowed workspace or user home directories. Traversal outside expected boundaries is currently unvalidated.
4. **Git Exposure of Personal Data & Runtime Logs**:
   - `contacts.csv` (contains actual names and phone numbers) is committed and tracked in git.
   - `logs/*.log` files (containing transcripts and system paths) are committed and tracked in git.
   - `database/*.db` (containing SQLite session history) are tracked in git.
   - `.gitignore` must be hardened immediately in Phase 1.
5. **Prompt Injection & Untrusted Data**:
   - Web search results, clipboard contents, and scraped webpage data are currently piped directly into strings without delimited encapsulation blocks or privilege separation.
6. **WhatsApp / Communication Fake Verification**:
   - `commands/whatsapp.py` sleeps 4 seconds and simulates `pyautogui.press("enter")`. If the browser tab has not loaded WhatsApp Web QR code or chat list, the keystroke is lost or delivered to an unintended window, yet the assistant reports `"Sent WhatsApp message"`.

### 5.2 Reliability Findings
1. **Unclosed SQLite Database Connections**:
   - Multiple methods in `database/database.py` and `database/chat_db.py` leak open database connections or file handles, as verified by `ResourceWarning: unclosed database in <sqlite3.Connection object>` during test execution.
2. **Missing Timeouts**:
   - Wake word thread loops continuously without bounded retry backoff.
   - Several subprocesses are spawned without timeout caps.
3. **Implicit Dependencies**:
   - `commands/system.py` relies on `nircmd.exe` in system PATH for volume control without checking if it exists or providing a fallback.

---

## 6. Branding Inventory

A complete grep of the repository identified old brand names across multiple categories.

### Category Breakdown:

| Category | Occurrences | Examples |
|---|---|---|
| **User-Facing UI** | 8 | Window titles (`"ASHISH AI — Personal Windows Voice Assistant"`, `"AYRA AI Settings"`), Header labels (`"ASHISH AI"`, `"ASHISH AI Settings"`), Chat timestamps, Orb state displays. |
| **Spoken Text & TTS** | 6 | Greetings (`"Hello! I am ASHISH AI..."`), Greeting triggers (`"hello ashish ai"`, `"hey ashish"`), default email subject (`"Message from ASHISH AI"`). |
| **Wake Words** | 5 | `"hey ashish"`, `"hey ayra"`, default configs in `.env`, `config/settings.py`, `ui/setting.py`. |
| **Documentation** | 42 | `README.md` title, badges, architectural diagrams, overview, commands. |
| **Configuration** | 6 | `.env` (`APP_NAME=ASHISH AI`, `WAKE_WORD=hey ashish`), `config/settings.py` (`APP_NAME`, `WAKE_WORD`), `config/voice_settings.json`. |
| **Logs & Loggers** | 12 | Logger names (`ayra.automation`, `ayra.database`, `ayra.voice`, `ashish.ai_service`, `ashish.youtube`), log files (`logs/ayra.log`). |
| **Database & Files** | 6 | `database/ayra_chat.db`, `database/ayra_memory.db`, `ayra_workspace/`, `database/database.py` (`AyraDatabase`). |
| **Author Attribution (TO PRESERVE)** | 4 | Author section in `README.md`, GitHub repository owner attribution, local user profile name (`Ashish`). **Rule 6 applies: MUST NOT be modified.** |

---

## 7. Baseline Test Execution Results

The existing test suite was executed in read-only mode to establish the baseline:

```bash
$env:PYTHONPATH=".;tests"; python -m unittest discover -s tests -t tests
```

### Result:
- **Ran 19 tests in 0.205s**
- **Status:** **OK (19/19 Passing)**
- **Test breakdown:**
  - `tests/test_assistant_upgrade.py`: 12 tests passed (Google opening, YouTube search/play, shortcuts, WhatsApp/Email confirmation formatting, contact ambiguity, local Ollama Q&A, offline fallback, Notepad launcher, current time).
  - `tests/test_gemini_client.py`: 7 tests passed (offline notice, zero models notice, online response, model auto-detection, greeting response, timeout handling, timeout env var).
- **Side-effecting tests omitted:** `tests/run_local_checks.py` was **NOT RUN** because it creates real test folders and files on the user's Desktop (`Path.home() / 'Desktop' / 'Ashish'`).
- **Resource Warnings Observed:**
  - `ResourceWarning: unclosed file database.log` in `database/database.py:25`
  - `ResourceWarning: unclosed database in <sqlite3.Connection object>` (19 warnings)
  - `Ollama query exception: Read timed out` (properly handled by mock test)

---

## 8. What to Preserve vs. What to Upgrade

### 8.1 What to PRESERVE (Working Core)
1. **Ollama Integration**: The existing dynamic endpoint discovery and model auto-detection in `ai/ai_service.py` is solid and works with `llama3.2:latest`. Wrap it inside the target `LLMProvider` interface.
2. **Command Automation Coverage**: 30+ Windows app shortcuts, 27 website bookmarks, YouTube direct playback, Open-Meteo weather API, contact ambiguity resolution, and CustomTkinter layout structure.
3. **HUD Orb Visual Aesthetic**: The CustomTkinter dark canvas orb with pulsating concentric rings and hardware telemetry layout is visually appealing and aligns with OLIVER 2.0 futuristic requirements.
4. **User Data**: Existing chat history in `ayra_chat.db`, reminders in `ayra_memory.db`, and address book entries in `contacts.csv`.
5. **Author Attribution**: "Ashish" as developer/author and user name.

### 8.2 What to UPGRADE
1. **Brand Identity**: Unify the fragmented "AYRA AI" / "ASHISH AI" brand into **OLIVER 2.0** across all user-facing surfaces, preserving author attribution and alias wake words.
2. **Modular Skill Architecture**: Transition from the monolithic `CommandRouter` and `AshishAssistant` to a decoupled `SkillRegistry`, `BaseSkill`, and typed `ToolSpec`/`ToolResult` contract.
3. **Deterministic Safety & Policy Engine**: Replace raw string prefixes (`"CONFIRMATION_REQUIRED:..."`) with a structured 4-tier Policy Engine (`Risk Level 0–3`) and single-action, expiring confirmations.
4. **Execution & Real Verification**: Replace blind assumption of success with an `Executor` and post-execution `Verifier` (checking process PIDs, window titles, file metadata, and read-backs). Mark WhatsApp as `UNVERIFIED` honestly.
5. **Local Voice Pipeline**: Replace cloud-dependent `recognize_google` in wake word and STT with an offline local engine (VAD + local Whisper/faster-whisper), while maintaining legacy fallback.
6. **Safety Hardening**: Replace `eval()` with safe AST evaluators; eliminate `shell=True`; enforce path allowlist sandboxing.
7. **Unified Memory Store**: Consolidate scattered SQLite databases into a migration-managed store with FTS5 search and explicit user privacy controls ("forget", export).
8. **Git Hygiene**: Add `.gitignore` coverage for databases, logs, captures, screenshots, and `.env`; untrack sensitive files without deleting local copies.

---

## 9. Proposed OLIVER 2.0 Target Mapping

```
Existing Component               OLIVER 2.0 Architecture Layer
-------------------------------------------------------------------------
main.py                          -> core/app.py (Composition Root)
config/settings.py               -> core/config.py (Pydantic / Typed Config)
logs/*                           -> core/logging.py (Structured, Correlated, Redacted)
(exceptions scattered)           -> core/errors.py (Typed Error Hierarchy)
ai/ai_service.py                 -> llm/providers/ollama_provider.py (LLMProvider Interface)
ai/assistant.py + router.py      -> router/intent_router.py + skills/registry.py
commands/windows.py + system.py  -> skills/builtin/windows_skill.py
commands/browser.py              -> skills/builtin/browser_skill.py
commands/youtube.py              -> skills/builtin/youtube_skill.py
commands/files.py                -> skills/builtin/files_skill.py (Sandboxed)
commands/whatsapp.py + email.py  -> skills/builtin/communication_skill.py
commands/contacts.py             -> skills/builtin/contacts_skill.py
commands/weather.py + news.py    -> skills/builtin/info_skill.py
commands/productivity.py         -> skills/builtin/productivity_skill.py (Safe AST)
database/* (3 separate DBs)      -> storage/db.py + memory/store.py (Unified SQLite)
(no policy engine)               -> security/policy_engine.py + confirmation.py
(no verifier)                    -> execution/executor.py + verification/verifier.py
voice/*                          -> voice/pipeline.py (VAD + Local STT + SAPI5 TTS)
ui/app.py + chat.py + setting.py -> hud/desktop_hud.py (Event Bus Driven)
```

---

## 10. Phased Implementation Plan Adjusted to Reality

- **Phase 0 (Current)**: Read-Only Audit & Approved Plan (Completed in `docs/AUDIT.md`). **GATE 0: STOP.**
- **Phase 1: Safety Baseline & Infrastructure**:
  - Git branch `oliver-2.0`, baseline tag `v1-baseline`.
  - Comprehensive `.gitignore` (untrack committed logs, databases, contacts without deleting local copies).
  - Timestamped SHA-256 verified user data backup to `backups/v1_baseline_<timestamp>/`.
  - Add `core/config.py`, `core/logging.py` (with secret redaction & correlation IDs), and `core/errors.py`.
  - Comprehensive regression suite in `tests/regression/` ensuring all 19 baseline capabilities remain green.
- **Phase 2: Skill / Tool / Plugin Architecture**:
  - Base `Skill`, `ToolSpec`, `ToolResult`, `SkillRegistry`.
  - Legacy adapter wrapping existing commands into skills without changing business logic.
  - Feature flag `router.mode: legacy | oliver`.
  - `LLMProvider` abstraction with `OllamaProvider`.
- **Phase 3: Security & Permission Manager**:
  - Policy Engine (Risk Levels 0 to 3).
  - Structured Confirmation Manager (exact effect previews, single-use, expiring).
  - Path sandbox (`Path.resolve`, allowlisted roots, Recycle Bin deletes).
  - Command sanitization (ban `shell=True`, remove `eval()`).
  - Append-only audit log `audit.jsonl`.
- **Phase 4: Central Execution & Verification Pipeline**:
  - Central `Executor`: Understand -> Plan -> Validate -> Policy -> Confirm -> Execute -> Verify -> Record -> Report.
  - Action verifiers using `psutil`, `pygetwindow`, filesystem inspection, and honest `UNVERIFIED` reporting (e.g., WhatsApp).
- **Phase 5: Context & Memory System**:
  - Unified SQLite store with schema migrations (`storage/`).
  - Idempotent additive import of existing chat messages (`ayra_chat.db`) and reminders (`ayra_memory.db`).
  - Multi-turn context manager, entity tracker, FTS5 memory retrieval, user memory control (view/forget/export).
- **Phase 6: Multi-Step Agent Mode**:
  - Bounded multi-step planner (max 6 steps, schema-validated, loop-detected).
  - Step-by-step verification gate and cancellation hotkey.
- **Phase 7: Professional Voice Pipeline**:
  - Voice engine flag `voice.engine: legacy | v2` (automatic fallback to legacy Google STT if v2 local models are absent).
  - Integrate local VAD + offline STT interface; interruptible TTS; measured latency reporting.
  - Transparent marking of Odia language support as experimental.
- **Phase 8: Capability Skills Expansion**:
  - Incremental sub-areas (8.1 Research, 8.2 Coding Assistant, 8.3 Documents/PDF, 8.4 Vision, 8.5 Browser Automation via Playwright, 8.6 Productivity, 8.7 Daily Briefing, 8.8 Communication Hardening).
- **Phase 9: Futuristic OLIVER HUD / Desktop UI**:
  - Decouple GUI from business logic via event bus.
  - Retain and elevate the CustomTkinter animated HUD orb with real-time state transitions and confirmation dialogs.
  - Complete user-facing rebranding to OLIVER.
- **Phase 10: Final Hardening, Testing, Documentation & Release Readiness**:
  - Full test suite execution (regression, security, agent, memory, unit).
  - Documentation suite (`README.md`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/CONFIG.md`, `docs/MIGRATION.md`, `docs/IMPLEMENTATION_REPORT.md`).

---

## 11. Assumptions & Non-Blocking Notes for Approval

1. **CustomTkinter Preservation**: The existing GUI is built in CustomTkinter with custom Canvas animations and responsive dark styling. We will keep CustomTkinter as the desktop UI engine rather than rewriting in another toolkit, decoupling it from logic via an internal EventBus.
2. **Author Attribution**: "Ashish Sahoo" / "Ashish" will remain preserved as the creator, developer, and default user name, while the assistant persona will be named **OLIVER** (version 2.0).
3. **Data Protection Priority**: In Phase 1, existing databases (`ayra_chat.db`, `ayra_memory.db`, `memory.db`) and `contacts.csv` will be copied to a timestamped backup directory with SHA-256 hashes recorded before any file is touched.
