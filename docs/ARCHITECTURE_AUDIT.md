# OLIVER 2.0 → OLIVER 3.0 Architecture Audit
**Phase 0 — Read-Only Audit**

> **Generated:** 2026-11-07 | **Auditor:** Antigravity AI (PHASE 0 — no code modified)
> **Target repo:** `c:\Users\ASHISH\OneDrive\Desktop\Documents\my own voice assistant`

---

## 1. Project Tree and Entry Points

### 1.1 How OLIVER Is Launched

```
python main.py          # Production entry point
```

[`main.py`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/main.py) (42 lines):
1. Loads `.env` via `python-dotenv`
2. Instantiates `OliverApp` → delegates to `AshishApp(ctk.CTk)` from `ui/app.py`
3. Calls `app.run()` which enters the CustomTkinter main-loop

### 1.2 Top-Level Directory Layout

```
my own voice assistant/
├── main.py                   # Entry point
├── .env / .env.example       # Secrets (env-vars; .env git-ignored)
├── requirements.txt          # Partial dep list (see §6)
├── agent/                    # Multi-step agent planner + executor
├── ai/                       # AI service layer (Ollama REST), memory helpers
├── assets/                   # Icons, images
├── ayra_workspace/           # Legacy scratch area
├── backups/                  # Pre-migration DB backups
├── browser/                  # Browser automation service + security
├── captures/                 # Screenshot capture directory
├── coding/                   # Coding assistant skill (analyze, diff, service)
├── commands/                 # Legacy command handlers (browser, contacts,
│                             #   calculator, email, reminders, router, system,
│                             #   whatsapp)
├── config/                   # AppSettings (legacy thin wrapper)
├── core/                     # OliverConfig (Pydantic), logging, correlation IDs
├── database/                 # SQLite stores + backups
│   ├── ayra_chat.db          # Legacy chat store (ChatStore class)
│   ├── ayra_memory.db        # Legacy reminder store (unused)
│   ├── memory.db             # Legacy user/notes store (unused)
│   ├── oliver.db             # PRIMARY unified store (schema V4, WAL)
│   └── backups/              # Pre-V3 and pre-V4 migration snapshots
├── docs/                     # Architecture docs, phase plans
├── execution/                # ExecutionEngine, TaskRequest, Verifiers
├── knowledge/                # Document index + FTS5 search skill
├── llm/                      # OllamaClient, OllamaProvider (LLM abstraction)
├── logs/                     # Runtime logs (voice.log, etc.)
├── memory/                   # HybridMemoryEngine (working/episodic/semantic)
├── productivity/             # ProductivityService, scheduler, models
├── research/                 # Web research skill + SSRF defense
├── router/                   # IntentRouter (deterministic + LLM fallback)
├── scratch/                  # Developer scratch / test scripts
├── screenshots/              # Screenshot storage
├── scripts/                  # Utility scripts
├── security/                 # PolicyEngine, KillSwitch, ConfirmationManager,
│                             #   PathSandbox
├── skills/                   # SkillRegistry, ToolSpec, builtin skills
├── tests/                    # Regression suite (252 tests, 100% pass)
├── ui/                       # CustomTkinter shell (app.py, chat.py,
│                             #   event_bridge.py, setting.py)
└── voice/                    # VoiceManager, VoiceListener, VoiceSpeaker,
                              #   STT engines, VAD, wake-word
```

---

## 2. Current Components

### 2.1 CustomTkinter UI (`ui/`)

| File | Responsibility |
|------|---------------|
| `ui/app.py` | `AshishApp(ctk.CTk)` — 3-column cockpit shell. Instantiates `AshishAssistant`, `ChatStore`, `VoiceManager`. Builds Left System Monitor, Center AI-Orb + Agent Monitor + Reminder Feed, Right Command Console. Runs system-telemetry polling via `psutil`. |
| `ui/chat.py` | `CommandConsolePanel` — text input, voice button, session sidebar, console log entries, confirmation modals, streaming AI token display, voice speak-on-sentence. **This is the heaviest coupling point.** |
| `ui/event_bridge.py` | `UIEventQueue` — thread-safe FIFO bridge; posts callables to Tk main thread via `root.after()`. |
| `ui/setting.py` | `VoiceSettingsWindow` — voice/speed/language settings form. |

**Tight couplings in `ui/chat.py`** (the primary seam for backend extraction):
- Imports `AshishAssistant`, `AIService.ask_stream`, `VoiceManager` directly
- Calls `voice_manager.speak()` inline in the token-streaming callback
- Calls `get_kill_switch()` before every execution
- Renders Tkinter widgets on background threads via `event_bridge.post()`

### 2.2 AI Provider Layer (`ai/`)

| File | Responsibility |
|------|---------------|
| `ai/ai_service.py` | `AIService` — Ollama REST client. Health check (15 s cache), streaming via `/api/chat`, fallback to `/api/generate`. Warmup keep-alive ping. TTFT logging. |
| `ai/assistant.py` | `AshishAssistant` — central brain. Routes text to: `CommandRouter`, `IntentRouter` (OLIVER mode), `HybridMemoryEngine`, `ProductivityService`, `AgentTaskLoop`, `AIService`. **Has duplicated `handle()` body** (copy-paste artifact). |
| `ai/memory.py` | `ConversationMemory` — in-process short-term ring buffer. |
| `ai/memory_manager.py` | `MemoryManager` — legacy notes/reminder helper (wraps older DB tables). |
| `ai/memory_prompt.py` | `MemoryPromptBuilder` — injects long-term memory into AI prompt. |
| `ai/gemini_client.py` | Legacy Gemini client (`.bak` variant exists). **Likely dead code.** |
| `ai/openaiclient.py` | Legacy OpenAI client. **Likely dead code.** |

### 2.3 Voice Recognition (STT) — `voice/stt/`

| File | Responsibility |
|------|---------------|
| `voice/stt/vosk_engine.py` | `VoskSTTEngine` — offline local Vosk. Locates model in `models/vosk/` or `~/.cache/vosk`. Falls back to `vosk.Model(lang=…)` auto-fetch. |
| `voice/stt/google_engine.py` | Google Cloud STT via `SpeechRecognition`. Online fallback when `fallback_external_allowed=True`. |
| `voice/stt/local_first.py` | `LocalFirstSTT` — tries Vosk first; falls back to Google if Vosk unavailable. |
| `voice/stt/base.py` | `SpeechToTextEngine` ABC + `TranscriptionResult` dataclass. |
| `voice/listener.py` | `VoiceListener` — `SpeechRecognition` audio capture with VAD/silence detection. |
| `voice/audio_capture.py` | `AudioCapture` — PyAudio stream wrapper. |
| `voice/vad.py` | Voice activity detection (energy-based silence timeout). |
| `voice/wakeword.py` | `WakeWordDetector` — "hey oliver" / "hey ashish" via `SpeechRecognition`. |

**Current STT status:** Vosk is the primary local engine. **No Whisper integration yet.**

### 2.4 TTS (`voice/speaker.py`)

`VoiceSpeaker` wraps **Windows SAPI5 via `pyttsx3`**:
- Dedicated synthesis worker thread for COM stability
- Sentence-level barge-in (stops mid-utterance)
- Preferred voice: Zira/female when available

> **No Piper TTS integration yet** — OLIVER 3.0 plan calls for Piper.

### 2.5 Browser Skills

| Module | Description |
|--------|-------------|
| `commands/browser.py` | `BrowserCommands` — lookup table of 50+ named sites, opens via `webbrowser.open()`. **Has one uncommitted modification** (`git status` shows `M commands/browser.py`). |
| `browser/service.py` | Selenium-based headless extraction service. |
| `browser/security.py` | SSRF defense + domain allowlist enforcement. |

### 2.6 Notes / Reminders / Productivity (`productivity/`)

`ProductivityService` — the main orchestrator:
- `ProductivityStore` — CRUD for `reminders`, `notes`, `user_tasks` tables in `oliver.db`
- `ProductivityScheduler` — background thread polls every 5 s, dispatches due reminders
- Calls `VoiceSpeaker.speak()` and fires registered dispatch listeners (UI `ReminderFeedPanel`)
- `DateTimeParser` — natural language date/time parsing
- Daily briefing via local Ollama

### 2.7 Agent Task Monitor (`agent/`)

`AgentTaskLoop`:
- Multi-step planner (`Planner` → Ollama LLM) + `PlanValidator` + `LoopDetector`
- Executes via `ExecutionEngine` funnel
- Persists task + step records to `oliver.db` (`agent_tasks`, `agent_task_steps`)
- Progress callback drives `AgentTaskMonitorCard` in `ui/app.py`
- Max 6 steps, max 1 replan, 60 s task timeout

### 2.8 Emergency Stop / Kill Switch (`security/kill_switch.py`)

Thread-safe singleton `KillSwitch`:
- `.activate()` → halts all voice output, revokes all confirmation tokens, blocks new tool calls
- `.deactivate()` requires modal confirmation
- Checked in `ui/chat.py` before every execution and in every streaming token callback

### 2.9 Memory System (`memory/`)

`HybridMemoryEngine` with 3 tiers (all in `oliver.db` WAL mode):
- **Working Memory** — session-scoped key/value store (`working_memory` table)
- **Episodic Memory** — per-session dialogue history (`messages` table)
- **Semantic Memory** — long-term facts/preferences (`memories` table), importance scoring

> **Note:** Legacy parallel stores exist: `ai/memory.py` (in-process ring buffer) and `database/ayra_chat.db` via `ChatStore`. These are not yet fully unified with the main store.

### 2.10 Skill / Execution Layer

| Component | Description |
|-----------|-------------|
| `skills/registry.py` | `SkillRegistry` — dynamic skill discovery and lifecycle |
| `skills/base.py` | `ToolResult`, `ToolSpec`, `SkillManifest`, `ToolRiskLevel` |
| `skills/builtin/` | Windows, Browser, Research, Coding, Knowledge, Productivity, AI skills |
| `execution/engine.py` | `ExecutionEngine` — `TaskRequest → Validate → PolicyGate → Confirm → Execute → Verify → Record` |
| `router/router.py` | `IntentRouter` — 50+ compiled regex rules first, then schema-constrained Ollama fallback |

---

## 3. SQLite Databases — Full Read-Only Audit

### 3.1 Active / Production Databases

#### `database/oliver.db` — PRIMARY (192,512 bytes, schema V4, WAL mode)

**Writer:** `memory/unified_db.py` (`UnifiedDatabase`)  
**Readers/Writers:** Nearly every backend module via `get_unified_db()` singleton

| Table | Rows | Key Columns | Writers |
|-------|------|-------------|---------|
| `schema_migrations` | 4 | version, name, applied_at | `UnifiedDatabase._initialize_database()` |
| `data_migration_log` | 9 | source_db, source_table, source_id, target_table, target_id, status | legacy migration scripts |
| `sessions` | 1 | session_id (TEXT UNIQUE), title, created_at, updated_at | `memory/episodic_memory.py` |
| `messages` | 8 | session_id, role, content, tokens_estimate, metadata | `EpisodicMemory.add_message()` |
| `memories` | 0 | category, key, content, importance, access_count | `SemanticMemory.add_memory()` |
| `working_memory` | 0 | session_id, key, value | `WorkingMemory.track_entity()` |
| `reminders` | 0 | title, remind_at, status, recurrence, priority, lease_until, dispatch_attempts | `ProductivityStore` |
| `notes` | 0 | title, content | `ProductivityStore` |
| `user_tasks` | 0 | title, description, due_date, priority, status | `ProductivityStore` |
| `agent_tasks` | 0 | task_id, goal, status, plan_json, current_step | `agent/persistence.py` |
| `agent_task_steps` | 0 | task_id, step_number, tool_name, arguments, status, verification_evidence | `agent/persistence.py` |
| `indexed_documents` | 0 | doc_id, file_path, file_hash, file_type | `knowledge/store.py` |
| `document_chunks` | 0 | chunk_id, doc_id, chunk_index, content | `knowledge/store.py` |
| `document_chunks_fts` | 0 | FTS5 virtual table over `document_chunks` | `knowledge/store.py` |
| `notes_fts` | 0 | FTS5 virtual table over `notes` | `ProductivityStore` |

#### `database/ayra_chat.db` — Legacy Chat Store (20,480 bytes)

**Writer/Reader:** `database/chat_db.py` (`ChatStore`)  
**Instantiated in:** `ui/app.py` as `self.store = ChatStore()` — but NOT wired to store actual messages. **Effectively unused in practice.**

| Table | Rows | Columns |
|-------|------|---------|
| `chat_sessions` | 1 | id, title, started_at, updated_at |
| `chat_messages` | 0 | id, session_id, role, content, created_at |

#### `database/ayra_memory.db` — Legacy Reminder Store (12,288 bytes)

Simple `reminders` table, 0 rows. Superseded by `oliver.db/reminders`. Read by old `MemoryManager` paths only.

#### `database/memory.db` — Legacy User/Notes Store (40,960 bytes)

Schema from early AYRA era: `users`, `chats`, `messages`, `memory`, `settings`, `reminders`, `notes`. All 0 rows. **Dead data, not read by any active code path in OLIVER 2.0.**

### 3.2 Backup Databases (read-only snapshots, never touched in production)

| Path | Description |
|------|-------------|
| `database/backups/oliver_pre_v3_*.db` | Automatic snapshot before V3 migration |
| `database/backups/oliver_pre_v4_*.db` | Automatic snapshot before V4 migration |
| `backups/pre_migration_*/` | Earlier hand-made migration backups |
| `backups/v1_baseline_*/` | Phase 1 baseline snapshot |

> [!CAUTION]
> Per Rule #2: No Phase 1 work should ever touch these backup files or any production database directly. All test code uses `isolated_test_db()` context manager or in-memory DB.

---

## 4. Git Status

```
Branch:    main   (tracking origin/main, up to date)
Alt branch available: oliver-2.0 (older, pre-merge state)

Uncommitted changes (working tree):
  M  commands/browser.py    ← modified but not staged

Recent commits (main):
  1a2d61b  Added new features.
  73eb9e8  Update chat.py
  ebd69fb  Create test_quick_commands.py
  0ac0eb6  Create sqlite_check.py
  ba1910c  Update voice_settings.json
```

> [!NOTE]
> The `FINAL_RELEASE_AUDIT.md` describes a state on branch `oliver-2.0` with 252 tests. The **current working branch is `main`** (not `oliver-2.0`). That work appears to have been merged or rebased to `main`.

> [!IMPORTANT]
> Per Rule #3: I have not changed branches, committed anything, or touched Git history. The single modified file `commands/browser.py` is noted; Phase 1 must not stage or commit it without your explicit approval.

---

## 5. Working Features vs. Broken Features

### ✅ Verified Working (by reading code + prior 252-test audit)

| Feature | Evidence |
|---------|----------|
| Local Ollama AI Q&A with streaming tokens | `ai/ai_service.py` — health check, `/api/chat` stream, fallback to `/api/generate`, TTFT logging |
| Intent routing (deterministic + LLM fallback) | `router/router.py` — 50+ compiled regex rules, `OllamaProvider` schema-constrained fallback |
| Windows app launch, screenshots, volume, lock | `skills/builtin/windows_skill.py` via `ExecutionEngine` |
| Browser site opening (Firefox) | `commands/browser.py` — 50+ named sites |
| Reminder scheduling + HUD dispatch | `productivity/service.py` + `scheduler.py`, `ReminderFeedPanel` in UI |
| Multi-step agent loop | `agent/executor.py` — planner, validator, loop detector, 60 s timeout |
| Agent Task Monitor UI card | `AgentTaskMonitorCard` in `ui/app.py` |
| Emergency Stop Kill Switch | `security/kill_switch.py` — thread-safe, blocks voice+execution+UI input |
| Dangerous command confirmation modal | `security/confirmation.py` + `ConfirmationModal` in `ui/app.py` |
| Semantic/episodic/working memory | `memory/manager.py` — `HybridMemoryEngine`, WAL SQLite |
| SQLite schema migrations V1–V4 | `memory/unified_db.py` — versioned, with verified backup before each migration |
| Document indexing + FTS5 search | `knowledge/` package — multi-format, BM25 ranking |
| Coding assistant (explain/review/generate/debug) | `coding/service.py` + `analyzer.py` + `diff_engine.py` |
| Research skill (web) | `research/service.py` with SSRF defense |
| Secret redaction in logs | `core/logging.py` `RedactedFormatter` |
| Path sandbox (filesystem allowlist) | `security/sandbox.py` — blocks Windows system dirs |
| Vosk offline STT pipeline | `voice/stt/vosk_engine.py` — loads from `models/vosk/` or `.cache/vosk` |
| SAPI5 TTS (pyttsx3) | `voice/speaker.py` — dedicated thread, barge-in support |
| Wake-word detection | `voice/wakeword.py` — "hey oliver" / "hey ashish" |
| System telemetry HUD | `psutil`-based CPU/RAM/battery/network metrics in `ui/app.py` |
| Thread-safe UI event bridge | `ui/event_bridge.py` `UIEventQueue` |
| Test suite (252 tests, 100% pass) | `docs/FINAL_RELEASE_AUDIT.md` — last verified Oct 28, 2026 |

### ⚠️ Known Issues / Bugs (from code reading + prior audit)

| Issue | Severity | Location |
|-------|----------|----------|
| **Duplicated `handle()` body** in `AshishAssistant` | Medium | `ai/assistant.py` lines 119–199 and 161–199 — the method body appears twice (copy-paste). The first copy has `request_id` parameter; second does not. The `request_id`-aware branch is unreachable via the second definition. |
| **`ChatStore` (`ayra_chat.db`) is instantiated but not used** | Low | `ui/app.py` line 509: `self.store = ChatStore()`. The chat console never calls `store.save_message()`. All actual conversation data goes to `oliver.db/messages` via `EpisodicMemory`. |
| **`database/memory.db` and `database/ayra_memory.db` are stale** | Low | Zero rows. No active code writes to them. Preserved per Rule #2. |
| **`requirements.txt` incomplete** | High | Missing `pydantic>=2.10.0`, `vosk>=0.3.45`, `beautifulsoup4>=4.12.0` (documented in FINAL_RELEASE_AUDIT H1 — may already be fixed on `main`). |
| **`google-generativeai` in requirements but unused** | Low | Flagged in prior audit M3. |
| **`ai/gemini_client.py` and `ai/openaiclient.py` are dead code** | Low | Not referenced by any active import path. `.bak` file also present. |
| **`ToolSpec` uses Pydantic V1 `class Config`** | Low | `skills/base.py` line 47 — emits deprecation warning under Pydantic V2. |
| **Uncommitted `commands/browser.py` modification** | Low/Tracking | Noted by `git status`. Content unknown — needs review before Phase 1. |
| **No Whisper STT yet** | Gap | OLIVER 3 plan specifies Whisper; only Vosk + Google fallback exist currently. |
| **No Piper TTS yet** | Gap | OLIVER 3 plan specifies Piper; only pyttsx3/SAPI5 exists currently. |

---

## 6. Dependencies and Python Version

**Python:** 3.13.5 (confirmed by `python --version`)

### Current `requirements.txt`

```
customtkinter>=5.2.2
Pillow>=10.2.0
python-dotenv>=1.0.1
pydantic>=2.10.0
requests>=2.31.0
vosk>=0.3.45
beautifulsoup4>=4.12.0
SpeechRecognition>=3.10.4
pyttsx3>=2.90
opencv-python>=4.9.0.80
pyperclip>=1.8.2
psutil>=5.9.8
pyaudio>=0.2.14 ; platform_system != "Linux"
```

> [!NOTE]
> The current `main` branch `requirements.txt` *does* include `pydantic`, `vosk`, and `beautifulsoup4`. The prior audit findings (H1) may have been fixed after the `FINAL_RELEASE_AUDIT.md` was written, or relate to the `oliver-2.0` branch state.

### FastAPI / Async Conflicts to Resolve in OLIVER 3.0

| Issue | Detail | Mitigation |
|-------|--------|-----------|
| **`pyttsx3` is not async-safe** | Uses COM threading internally. Cannot be called from an `asyncio` event loop. | Existing `VoiceSpeaker` already isolates it on its own thread — preserve this pattern. |
| **`sqlite3` with `check_same_thread=False`** | `UnifiedDatabase` already sets this + uses `threading.Lock`. | Compatible with FastAPI via `run_in_executor`. |
| **`psutil` polling** | Blocking I/O. | Use `asyncio.to_thread()` or threadpool executor from a FastAPI background task. |
| **`vosk`** | CPU-bound + blocking. | `run_in_executor`. |
| **`requests` (sync HTTP to Ollama)** | The existing `AIService.ask_stream()` is synchronous. | Replace with `httpx.AsyncClient` for the FastAPI backend's AI calls. |
| **CustomTkinter** | Must remain on the main thread. | No conflict — desktop UI stays in its own process. |
| **`selenium` / browser automation** | Blocking. | Thread pool executor. |

---

## 7. Coupling Seams — Where the Backend Must Be Introduced

These are the specific code locations where the backend extraction must happen. Each is a **"seam"** — a point where the monolith can be cut to expose a service interface.

### Seam 1 — AI Q&A Streaming (Highest Priority)

**Location:** `ui/chat.py` `_run_assistant_command()` ≈ lines 460–514

```python
# CURRENT (tightly coupled):
reply_text = self.assistant.ai_service.ask_stream(command, on_token=on_token)
# on_token calls voice_manager.speak() inline
# No way to call from Flutter or a mobile client

# OLIVER 3 TARGET:
# Backend: POST /api/chat → streams tokens over WebSocket /ws/chat
# Desktop: WebSocket client replaces direct AIService call
# Mobile:  WebSocket client (Flutter) connects to same endpoint
```

### Seam 2 — Command Routing + Tool Execution

**Location:** `ui/chat.py` ≈ lines 516–590 and `ai/assistant.py` `handle_result()`

```python
# CURRENT:
res = self.assistant.handle_result(command)
# Runs IntentRouter + ExecutionEngine synchronously on a daemon thread inside the UI process

# OLIVER 3 TARGET:
# Backend: POST /api/command → returns ToolResult JSON
```

> [!WARNING]
> Windows-specific tools (`windows.open_app`, `windows.lock_computer`, etc.) must still run on the Windows host. The backend must run on the same Windows machine, or forward those tool calls to a local Windows agent.

### Seam 3 — STT (Voice Input)

**Location:** `voice/voice_manager.py` `listen_once()` and `ui/chat.py` `start_voice_input()`

```python
# CURRENT:
text = self.voice_manager.listen_once(...)
# Blocks until mic captures audio; called from a daemon thread in the UI

# OLIVER 3 TARGET (Desktop):
# Keep VoiceManager on-device — microphone stays local
# Desktop STT result posted to backend via POST /api/chat

# OLIVER 3 TARGET (Mobile Flutter):
# Flutter records audio → POST /api/stt (Whisper endpoint on backend)
```

### Seam 4 — TTS (Voice Output)

**Location:** `voice/voice_manager.py` `speak()` and inline in `ui/chat.py` `on_token` callback

```python
# CURRENT:
self.voice_manager.speak(tail, wait=False)
# Calls pyttsx3 SAPI5 — strictly Windows COM, runs on the dedicated speaker thread

# OLIVER 3 TARGET:
# Desktop: keep pyttsx3/Piper local — TTS is always local
# Mobile: backend sends audio stream (Piper WAV) to Flutter client
# Seam: backend POST /api/tts returns audio bytes OR streams via WebSocket
```

### Seam 5 — Memory Read/Write

**Location:** `memory/manager.py` `get_memory_engine()` singleton

```python
# CURRENT:
engine = get_memory_engine()   # process-local singleton, writes to oliver.db

# OLIVER 3 TARGET:
# Backend owns oliver.db exclusively
# Desktop & Mobile read/write memory via REST (GET/POST /api/memory)
# No direct SQLite access from desktop or mobile process
```

### Seam 6 — Productivity / Reminder Scheduler

**Location:** `productivity/service.py` `get_productivity_service()` + `ui/app.py` `ReminderFeedPanel`

```python
# CURRENT:
prod_srv = get_productivity_service()   # starts background scheduler thread inside UI process
self.reminder_feed = ReminderFeedPanel(..., productivity_service=prod_srv)

# OLIVER 3 TARGET:
# Scheduler runs in backend as a FastAPI background task (asyncio)
# UI subscribes via WebSocket (WS /ws/reminders) for push notifications
```

---

## 8. Proposed OLIVER 3.0 Target Folder Layout

### 8.1 Directory Structure

```
my own voice assistant/           ← Git root (all existing code preserved as-is)
│
├── backend/                      ← NEW: FastAPI server (additive, never overwrites existing)
│   ├── main.py                   # uvicorn entry point
│   ├── api/
│   │   ├── chat.py               # POST /api/chat, WS /ws/chat
│   │   ├── voice.py              # POST /api/stt, POST /api/tts
│   │   ├── memory.py             # GET/POST /api/memory
│   │   ├── reminders.py          # CRUD /api/reminders, WS /ws/reminders
│   │   ├── tasks.py              # CRUD /api/tasks
│   │   └── health.py             # GET /api/health
│   ├── services/
│   │   ├── ai_service.py         # Async wrapper (httpx) around Ollama
│   │   ├── memory_service.py     # Thin async wrapper → HybridMemoryEngine
│   │   ├── voice_service.py      # Whisper STT + Piper TTS
│   │   └── scheduler_service.py  # Async reminder scheduler
│   ├── auth/
│   │   └── user_auth.py          # User ID middleware (Rule #10)
│   └── requirements.txt          # fastapi, uvicorn, httpx, piper-tts, etc.
│
├── mobile/                       ← NEW: Flutter/Dart app
│   └── oliver_mobile/
│       ├── lib/
│       │   ├── main.dart
│       │   ├── screens/
│       │   └── services/
│       │       ├── chat_service.dart
│       │       ├── voice_service.dart
│       │       └── memory_service.dart
│       └── pubspec.yaml
│
├── docs/                         ← Existing docs + new 3.0 docs
│   ├── OLIVER_3_PLAN.md          ← (provided by user — not yet present)
│   ├── ARCHITECTURE_AUDIT.md     ← THIS FILE
│   └── ...existing docs...
│
│   [All existing top-level dirs remain completely untouched]
├── agent/    ai/    browser/    coding/    commands/    config/
├── core/     database/          execution/ knowledge/   llm/
├── memory/   productivity/      research/  router/      security/
├── skills/   tests/             ui/        voice/
└── main.py   requirements.txt   .env       .env.example
```

> [!IMPORTANT]
> The existing OLIVER 2.0 code stays **exactly** where it is. The backend is an *additive* new directory that imports and wraps existing services. The desktop UI is updated minimally to call the backend API instead of calling services directly.

### 8.2 Step-by-Step Migration Plan

| Phase | Step | What Changes | Risk |
|-------|------|-------------|------|
| **Phase 1** | Backend scaffold | Create `backend/` with FastAPI skeleton, health endpoint, `.env` wiring. Import existing `OliverConfig`. Run alongside desktop with no UI changes. | **LOW** — purely additive |
| **Phase 2** | AI endpoint | Extract `AIService` async wrapper. Add `POST /api/chat` and `WS /ws/chat`. Add `httpx` dependency. Desktop UI connects to backend for AI Q&A, with fallback to direct call. | **MEDIUM** — first seam cut; test streaming latency |
| **Phase 3** | Command execution endpoint | Wrap `AshishAssistant.handle_result()` in `POST /api/command`. Desktop calls backend. Windows-local tools still execute on the Windows host (backend runs locally). | **MEDIUM** — confirmation flow must be preserved end-to-end |
| **Phase 4** | Memory API | Add `GET/POST /api/memory` endpoints wrapping `HybridMemoryEngine`. Backend owns `oliver.db` exclusively. No more direct SQLite from UI process. | **LOW-MEDIUM** — SQLite concurrency already safe with WAL |
| **Phase 5** | Productivity / Reminder WebSocket | Move scheduler to backend async task. Add `WS /ws/reminders`. Desktop subscribes. | **MEDIUM** — scheduler threading model changes |
| **Phase 6** | STT / TTS endpoints | Add `POST /api/stt` (Whisper) and `POST /api/tts` (Piper). Desktop continues using local pyttsx3; mobile uses backend endpoints. | **LOW** — desktop voice unchanged; new endpoints for mobile only |
| **Phase 7** | Flutter mobile app | Build Flutter UI consuming the backend REST+WebSocket API. | **HIGH** — new platform; Dart/Flutter skills required |
| **Phase 8** | PostgreSQL (optional) | For multi-device sync: add PostgreSQL mirror of key tables. Desktop remains SQLite-first (offline). | **HIGH** — schema migration, data integrity risks |

### 8.3 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Windows tool calls require backend to run locally | Certain | High | Backend runs on same Windows machine; no remote execution needed initially |
| `pyttsx3` SAPI5 COM crashes if called from async context | Medium | High | Keep `VoiceSpeaker` on its own thread; never `await` voice calls |
| `oliver.db` corruption if desktop and backend both write directly | Medium | Critical | Backend owns DB exclusively after Phase 4; desktop reads/writes via API |
| Streaming token latency degradation over local HTTP vs. direct call | Low | Medium | Measure baseline first; local loopback latency is typically < 1 ms |
| Flutter app auth/session handling | Medium | High | Use user_id header + JWT; implement per Rule #10 from day one |
| Vosk model missing on fresh install | Medium | Medium | Backend startup check; fail fast with clear error message |

---

## 9. Backup Checklist — Must Complete Before Phase 1

> [!CAUTION]
> Do NOT start Phase 1 until every item below is checked.

- [ ] **1. Full directory backup** — copy the entire `my own voice assistant` folder to a safe location (external drive, different OneDrive path, or ZIP archive). Git stash is not a substitute.
- [ ] **2. Database backup** — manually copy `database/oliver.db`, `database/ayra_chat.db`, and `database/ayra_memory.db` to a location **outside** the project directory. The existing auto-backup snapshots in `database/backups/` are good but not sufficient alone.
- [ ] **3. Review `commands/browser.py` modification** — run `git diff commands/browser.py` and confirm: keep the change (I will help you commit it cleanly before Phase 1), or restore the tracked version.
- [ ] **4. Confirm branch** — you are on `main`. Confirm this is the correct branch to build on. If you want a separate branch (e.g. `oliver-3.0`), tell me and I will instruct you to create it; I will not do it myself per Rule #3.
- [ ] **5. Share `docs/OLIVER_3_PLAN.md`** — the plan file does not exist in the `docs/` directory. Please either share its content or create it so I can reference exact phase requirements before writing Phase 1 code.
- [ ] **6. Verify Ollama is running** — confirm `ollama run llama3.2` or equivalent is active. Phase 1 integration tests will need it.
- [ ] **7. Note Vosk model location** — confirm the Vosk model path (`models/vosk/` or `~/.cache/vosk/vosk-model-*`) so the backend STT phase can reference it correctly.

---

## 10. Questions That Need Your Answers Before Phase 1

1. **Plan document location:** `docs/OLIVER_3_PLAN.md` does not exist in the repository. Did you intend to include it, or is it a document you will share separately? This document is referenced throughout the instructions.

2. **Backend host:** Will the FastAPI backend run on the **same Windows machine** as the desktop app (most practical for Phase 1), or on a separate server/cloud machine? This determines whether Windows-specific tools (shutdown, app launch) can be called from the backend directly.

3. **`commands/browser.py` modified file:** `git diff commands/browser.py` shows uncommitted changes. Do you want to commit these changes before Phase 1, discard them, or leave them as-is?

4. **PostgreSQL vs. SQLite for backend:** The plan mentions PostgreSQL as a shared database. For Phase 1, should I use **SQLite exclusively** (zero migration risk) or start wiring PostgreSQL from day one?

5. **User authentication scope for Phase 1:** Rule #10 requires user ID authorization on every server resource. For Phase 1 (desktop-only, before the mobile app exists), is a **single hard-coded user ID** (you, Ashish) acceptable, or do you want a real auth layer from the start?

6. **Piper TTS — is it already installed?** Piper is in the OLIVER 3 plan but not in the current codebase. Do you have Piper installed (`piper-tts` Python package or standalone binary)? If not, should Phase 1 skip the TTS backend and keep pyttsx3?

7. **Whisper STT — which variant?** The plan specifies Whisper for STT. Do you prefer `openai-whisper` (Python, CPU/GPU), `faster-whisper`, or `whisper.cpp`? Do you have a GPU available?

8. **Mobile first target:** Should the Flutter mobile app target **Android only** initially, or both Android and iOS?

9. **Windows Task Scheduler integration:** The plan mentions Windows Task Scheduler. What specific tasks should it schedule? (e.g., daily briefing on startup, reminder dispatcher as a separate process, nightly database backup?)

10. **`ai/assistant.py` duplicate `handle()` body:** There is a duplicated method body (lines 119–199 and 161–199). The first copy (with `request_id`) is the live one; the second is dead code. Should I include a minimal fix for this bug in Phase 1 (additive, non-breaking), or leave it untouched per Rule #1?

---

## Summary

OLIVER 2.0 is a **fully functional, well-tested Windows desktop AI assistant** with:
- **252 regression tests, all passing** (last verified Oct 28, 2026)
- **Local-first architecture** (Ollama LLM, Vosk STT, SAPI5 TTS, SQLite WAL)
- **Strong security model** (PolicyEngine, KillSwitch, path sandbox, zero eval/shell=True)
- **Well-defined execution funnel** (ExecutionEngine → SkillRegistry → verified ToolResult)
- **6 clearly identified backend extraction seams** (AI streaming, command routing, STT, TTS, memory, productivity)

The primary challenge for OLIVER 3.0 is **introducing the FastAPI backend additively** without breaking the existing UI, with the highest-risk seam being Windows-local tool execution that must continue to run on the Windows host even after a backend is introduced.

---

*Phase 0 audit complete. No files modified. Awaiting your answers to §10 questions and confirmation that the §9 backup checklist is complete before Phase 1 begins.*

