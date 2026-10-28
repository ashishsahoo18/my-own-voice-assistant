# 🚀 OLIVER 2.0 — Windows AI Cockpit
**Autonomous Voice & Task Assistant for Windows**

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6?logo=windows&logoColor=white)](#system-requirements--prerequisites)
[![Python](https://img.shields.io/badge/Python-3.10%20--%203.13-3776AB?logo=python&logoColor=white)](#system-requirements--prerequisites)
[![AI Engine](https://img.shields.io/badge/Local%20AI-Ollama%20%7C%20Llama%203.2-FF6F00?logo=ollama&logoColor=white)](#local-ai-architecture)
[![Interface](https://img.shields.io/badge/GUI-CustomTkinter%20HUD-00D2FF)](#1-cockpit-hud--desktop-ui)
[![Tests](https://img.shields.io/badge/Tests-252%20Passing-success)](#testing--verification)
[![License](https://img.shields.io/badge/License-Not%20Declared-lightgrey)](#license)

> **OLIVER 2.0** is an intelligent, privacy-conscious desktop cockpit and autonomous voice assistant built natively for Windows. Powered locally by **Ollama** and **Llama 3.2**, it requires **zero paid cloud API keys** for its core intelligence, featuring local-first speech recognition, multi-step agent planning, live system telemetry, and an authoritative central security policy gate.

---

## 📑 Table of Contents

- [Overview & Philosophy](#overview--philosophy)
- [Key Architectural Highlights](#key-architectural-highlights)
- [Core Capabilities](#core-capabilities)
  - [1. Cockpit HUD & Desktop UI](#1-cockpit-hud--desktop-ui)
  - [2. Voice Pipeline & Speech Processing](#2-voice-pipeline--speech-processing)
  - [3. Autonomous Multi-Step Agent Loop](#3-autonomous-multi-step-agent-loop)
  - [4. Five Local Skills](#4-five-local-skills)
  - [5. Windows Desktop Automation](#5-windows-desktop-automation)
  - [6. Communication & Web Integrations](#6-communication--web-integrations)
- [Security Architecture & Safety Engine](#security-architecture--safety-engine)
- [Data Persistence & Concurrency](#data-persistence--concurrency)
- [System Requirements & Prerequisites](#system-requirements--prerequisites)
- [Installation & Setup Guide](#installation--setup-guide)
- [Running OLIVER 2.0](#running-oliver-20)
- [Testing & Verification](#testing--verification)
- [Troubleshooting & Known Limitations](#troubleshooting--known-limitations)
- [Author & Attribution](#author--attribution)
- [License](#license)

---

## 📌 Overview & Philosophy

**OLIVER 2.0** bridges local machine intelligence, real-time Windows hardware monitoring, and safe OS automation into a unified desktop cockpit.

### Core Design Principles

1. **Local-First & Offline-Capable Intelligence**:
   - Primary conversational generation runs locally on your workstation using **Ollama** (`llama3.2`) at `http://localhost:11434`.
   - Speech-to-text prioritizes an offline **Vosk** acoustic model. An optional, configurable fallback to Google Web Speech API is supported via `SpeechRecognition` when connected to the internet and explicitly allowed.
   - Speech synthesis operates offline via native Windows SAPI5 (`pyttsx3`).
   - Web search, weather forecasts, and browser navigation reach the internet when requested, but core assistant features, file operations, system controls, and memory operate locally.
2. **Zero `eval()` and Zero `shell=True`**:
   - Raw string execution hooks have been eradicated from production code. Arithmetic expressions are parsed safely using Python's `ast` module (`ast.parse`); all subprocesses invoke explicit argument lists (`shell=False`).
3. **Safety by Design & Central Policy Gate**:
   - Central `PolicyEngine` evaluates every tool invocation against 4 strict Risk Tiers before execution.
   - Sensitive and dangerous actions require explicit user confirmation via action-bound, single-use UUID tokens (`uuid.uuid4`) with time-to-live (TTL) expiration.
   - Filesystem sandboxing enforces canonical path checks against `allowlist_roots`, blocks protected system directories (`C:\Windows`, `C:\Program Files`) and credential folders (`.ssh`, `.aws`, browser profiles), and routes deletions to the Windows Recycle Bin via the Win32 Shell API (`SHFileOperationW`).
4. **Thread-Safe Cockpit Event Bridge**:
   - The CustomTkinter graphical interface is decoupled from background workers using a synchronized `UIEventQueue` bridge, preventing cross-thread GUI exceptions and ensuring bounded shutdown.

---

## ⚡ Key Architectural Highlights

| Subsystem | Verified Implementation in Repository |
|---|---|
| **AI Engine** | Local Ollama REST client communicating with `llama3.2:latest` on `localhost:11434` |
| **Speech-to-Text (STT)** | Hybrid `LocalFirstSTTEngine`: Primary offline `VoskSTTEngine` with optional fallback |
| **Text-to-Speech (TTS)** | Native offline Windows SAPI5 via `pyttsx3` with dynamic voice barge-in interruption |
| **Cockpit HUD** | Multi-threaded `customtkinter` with animated glowing Canvas Orb and responsive event bridge |
| **System Telemetry** | Live background polling via `psutil`: CPU %, RAM %, Battery %, Hardware Mic Privacy, and Kill Switch |
| **Security Gate** | Central `PolicyEngine` with 4 Risk Tiers, single-use UUID confirmation tokens, and `KillSwitch` |
| **Persistence Engine** | SQLite database (`database/oliver.db`) in WAL mode with schema migrations V1–V4 and FTS5 search |
| **Browser Driver** | Hardened ephemeral Selenium WebDriver (Edge / Chrome) with `SafeHTTPClient` fallback |

---

## ✨ Core Capabilities

### 1. Cockpit HUD & Desktop UI
- **Triple-Column Cockpit Layout**:
  - **Left Panel**: Real-time system telemetry indicators (`OLLAMA`, `VOICE`, `MIC PRIVACY`, `SCHEDULER`, `KILL SWITCH`), CPU/RAM/Battery hardware metrics, and Emergency Stop button.
  - **Center Stage**: Animated rotating glowing Canvas Orb reflecting operational states (`READY`, `LISTENING`, `PROCESSING`, `EXECUTING`, `SPEAKING`, `ERROR`, `KILLED`), live `AgentTaskMonitorCard` with progress bar, and HUD Reminder feed drawer.
  - **Right Panel**: Command Console with active speech transcript, 8 quick-action buttons, text input entry, and a chronological event log with truthful status badges (`VERIFIED`, `UNVERIFIED`, `FAILED`, `DENIED`, `CANCELLED`, `TIMEOUT`, `NEED_CONFIRM`).
- **Interactive Modals**: Toplevel modal overlays for parameter inspection, action confirmation, and emergency stop reset.

### 2. Voice Pipeline & Speech Processing
- **Push-to-Talk & One-Shot Listening**: Dedicated microphone capture triggered via the console HUD or programmatic hooks.
- **Ambient Noise Calibration**: Samples background noise for 0.5 seconds before listening to compute dynamic energy thresholds.
- **Speech Interruption (Barge-in)**: Triggering the Emergency Stop or speaking while OLIVER is talking halts audio synthesis immediately via `voice_manager.barge_in()`.
- **Hardware Privacy Telemetry**: Real-time microphone activity detection reflecting active vs. muted hardware state in the HUD.

### 3. Autonomous Multi-Step Agent Loop
- **Sequential Task Planning**: Validated multi-step plan execution loop (`AgentTaskLoop`) with step validation, loop detection, and state persistence.
- **Truthful Progress Reporting**: Dispatches live progress notifications (`planning`, `executing_step`, `waiting_for_confirmation`, `completed`, `failed`, `cancelled`) to the HUD.
- **Cooperative Cancellation**: Users can click `[ CANCEL TASK ]` to stop the loop between execution steps. Active atomic steps finish safely before the loop halts and records the status as `CANCELLED`.

### 4. Five Local Skills
1. **Productivity Skill**:
   - Manages tasks, recurring reminders, and notes stored in SQLite (`database/oliver.db`).
   - Natural language date/time parser with relative time expressions (`"tomorrow at 3pm"`, `"in 20 minutes"`).
   - Full-text search over notes using SQLite FTS5.
   - Background scheduler daemon with HUD reminder card delivery and idempotent acknowledgment.
2. **Browser Automation Skill**:
   - Hardened **Selenium WebDriver** session (Edge or Chrome) using ephemeral temporary user profiles (inprivate/incognito, downloads disabled).
   - Pre-flight and post-navigation URL validation against strict domain allowlists and anti-SSRF IP filters.
   - Pure **`SafeHTTPClient`** fallback (`urllib`/`requests` + `BeautifulSoup`) when Selenium is not installed or unavailable.
   - Prompt injection defense: Untrusted webpage text is defused of hostile directives and quarantined in `<untrusted_web_context>` XML envelopes.
3. **Documents & Knowledge Skill**:
   - Local document search and question-answering with source citations.
   - Pure-Python binary PDF stream decoding and zlib decompression (requires no external PDF CLI tool).
   - SQLite FTS5 passage storage with built-in `bm25()` ranking.
   - Defuses prompt injections in document content prior to query synthesis.
4. **Coding Assistant Skill**:
   - Safe AST-based static code analysis detecting syntax errors, complexity, and security anti-patterns.
   - Unified diff patch engine applying modifications exclusively within configured workspace sandboxes.
   - Automated secret redactor: Masks API tokens (`sk-`, `ghp-`, `AKIA-`), database URIs, and private keys from logs and prompts.
5. **Research Assistant Skill**:
   - Multi-query search synthesis across approved web endpoints (requires internet access).
   - Outbound SSRF protection: Blocks RFC1918 private subnets, cloud metadata (`169.254.0.0/16`), loopback (`127.0.0.1`, `::1`), and IPv4-mapped IPv6 addresses.
   - Fact extraction with transparent source URL citations.

### 5. Windows Desktop Automation
- **Application Launcher**: Native launch support for Windows apps:
  - Notepad, Calculator, Paint, File Explorer, Task Manager, Control Panel, Command Prompt, PowerShell, Windows Settings (`ms-settings:`).
  - VS Code, Google Chrome, Microsoft Edge, Firefox, Brave, Spotify, VLC, Zoom, Teams, Discord, Word, Excel.
- **System Controls**:
  - Lock workstation (`ctypes.windll.user32.LockWorkStation`).
  - Restart Explorer (`taskkill /f /im explorer.exe` followed by `explorer.exe`).
  - Sleep (`rundll32.exe powrprof.dll,SetSuspendState Sleep`).
  - Log out (`shutdown /l`).
  - Safe system shutdown (`shutdown /s /t 5`) and restart (`shutdown /r /t 5`), strictly intercepted by the confirmation policy gate.
- **Recycle Bin Deletion**: File and directory deletions use Win32 `SHFileOperationW` (`FO_DELETE` with `FOF_ALLOWUNDO`), moving files safely to the Windows Recycle Bin rather than permanently unlinking them.

### 6. Communication & Web Integrations
- **WhatsApp Web Integration**: Prepares pre-filled message URLs in the default browser and attempts simulated keystroke dispatch via PyAutoGUI after user confirmation (requires an active WhatsApp Web login in the browser).
- **Email Service**: Dual-mode email handling (direct Gmail SMTP SSL if credentials exist in `.env`, or browser-based Gmail web compose fallback), intercepted by the confirmation gate before dispatch.
- **Contact Manager**: CSV contact resolution (`contacts.csv`) with automatic ambiguity detection prompting the user when queries match multiple contacts.
- **YouTube Helper**: Search queries open YouTube results in the browser; play commands extract matching video IDs via search requests and schedule playback.
- **Weather Forecast**: Queries the Open-Meteo public geocoding and forecast API (`https://api.open-meteo.com`) for temperature and wind conditions (requires internet access).

---

## 🔒 Security Architecture & Safety Engine

```
[User Input / Voice Command]
             │
             ▼
      [IntentRouter]
             │
             ▼
     [PolicyEngine] ◄── [KillSwitch State]
             │
   ┌─────────┴───────────────────────┐
   ▼                                 ▼
[Risk 0 / 1: Safe]         [Risk 2 / 3: Sensitive / Dangerous]
   │                                 │
   │                        Create Single-Use Token (UUID + TTL)
   │                                 │
   │                        Display ConfirmationModal (Exact Preview)
   │                                 │
   │                        ┌────────┴────────┐
   │                        ▼                 ▼
   │                   [Confirmed]       [Cancelled]
   │                        │                 │
   │                        │            Invalidate Token
   │                        ▼                 │
   └───────────────► [ExecutionEngine] ◄──────┘
                            │
                            ▼
                    [Tool Execution]
                            │
                            ▼
                   [VerifierRegistry]
                            │
                            ▼
              [Truthful ToolResult to UI]
```

### Risk Tiers
- **Risk 0 (Safe)**: Non-mutating queries (time, date, battery status, safe calculator math). Auto-allowed.
- **Risk 1 (Low)**: Standard non-destructive operations (listing directories, searching notes, checking daily agenda). Auto-allowed with audit record.
- **Risk 2 (Sensitive)**: State modifications (writing files, moving folders, deleting notes/tasks, sending messages or emails). Strictly requires user confirmation.
- **Risk 3 (Dangerous)**: Critical workstation actions (shutdown, reboot, sleep, logout, process termination). Strictly requires human confirmation via modal dialog.

### Emergency Stop (Kill Switch)
- Accessible at all times via the `🚨 EMERGENCY STOP` button in the Left Panel.
- Engaging the kill switch immediately halts audio output (`barge_in`), revokes all pending confirmation tokens, blocks all tool execution, and locks the Command Console.
- Disengaging requires explicit user confirmation via a safety reset modal.

---

## 💾 Data Persistence & Concurrency

- **Unified SQLite Store**: Stored at `database/oliver.db` using Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and `PRAGMA synchronous = NORMAL;`.
- **Thread-Local Connections**: SQLite connection handles are isolated per-thread (`threading.local`) to ensure thread-safe concurrent access.
- **Schema Migrations**: Automated versioning tracked in `schema_migrations`:
  - `V1`: Unified memories, categories, and conversation history.
  - `V2`: Agent tasks and execution step store.
  - `V3`: Document knowledge store with SQLite FTS5 index.
  - `V4`: Productivity tasks, reminders, notes, and notes FTS5 index.
- **Verified Backups**: Migration V4 flushes WAL frames (`PRAGMA wal_checkpoint(TRUNCATE)`) and executes the SQLite Online Backup API to save verified backups in `database/backups/`.
- **Integrity Checks**: Built-in verification via `UnifiedDatabase.check_integrity(quick=False/True)` executing `PRAGMA integrity_check` and `PRAGMA quick_check`.

---

## 💻 System Requirements & Prerequisites

- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Python**: Version 3.10, 3.11, 3.12, or 3.13 (tested on Python 3.13.5).
- **Audio Hardware**: Working microphone and speakers / headphones.
- **Local AI Engine**: [Ollama for Windows](https://ollama.ai) installed and running.
  - Recommended model: `llama3.2` (3B parameters) or `llama3.2:1b`.
- **C++ Runtime**: Microsoft Visual C++ 2015–2022 Redistributable (required for `pyaudio` and `vosk` on Windows).

---

## 🚀 Installation & Setup Guide

### 1. Clone the Repository
```powershell
git clone -b oliver-2.0 https://github.com/ashishsahoo18/my-own-voice-assistant.git
cd "my own voice assistant"
```

### 2. Create and Activate Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the example configuration to `.env`:
```powershell
Copy-Item .env.example .env
```
*(Review `.env` to customize preferences, optional email credentials, or custom model paths. Secrets are never tracked by Git).*

### 5. Setup Local AI (Ollama)
Ensure the Ollama service is active and pull the primary Llama 3.2 model:
```powershell
ollama pull llama3.2
```
Verify Ollama is reachable at `http://localhost:11434`.

### 6. Setup Offline Speech Model (Vosk)
OLIVER 2.0 locates Vosk models in any of the following locations:
1. Custom path set in `.env`: `VOICE_VOSK_MODEL_PATH=C:\path\to\model`
2. Project directory: `models/vosk`
3. User cache: `C:\Users\<Username>\.cache\vosk\vosk-model-small-en-us-0.15`
4. Local app data: `%LOCALAPPDATA%\vosk`

If no local model is found, the engine attempts an initial download via `vosk.Model(lang="en-us")` if internet access is available. For completely air-gapped setups, extract [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models) into one of the directories above.

---

## 🖥️ Running OLIVER 2.0

Launch the Cockpit HUD:
```powershell
python main.py
```

### Headless Verification
To verify the application pipeline without launching the graphical display server:
```powershell
python -m unittest discover -s tests/regression -p "test_*.py"
```

---

## 🧪 Testing & Verification

The repository includes a comprehensive, non-destructive regression test suite verified on Python 3.13:

```powershell
python -m unittest discover -s tests/regression -p "test_*.py"
```

### Verified Test Suite Breakdown (252 Regression Tests Passing)

| Test Module | Tests | Focus Area |
|---|---|---|
| `test_ui_pipeline.py` | 38 | UI event bridge, status badges, kill switch, agent monitor, bounded shutdown |
| `test_security_policy.py` | 22 | Central PolicyEngine, token expiration, AST zero-eval assertion |
| `test_productivity_skill.py` | 21 | Tasks, reminders, notes, datetime parser, recurrence, scheduler |
| `test_memory_engine.py` | 21 | SQLite WAL storage, memory privacy filters, conversation turns |
| `test_baseline_parity.py` | 20 | Base command dispatching parity across system categories |
| `test_coding_skill.py` | 19 | AST static analysis, patch engine, workspace sandbox, secret redaction |
| `test_knowledge_skill.py` | 16 | FTS5 BM25 search, pure-Python PDF decoding, chunking, citations |
| `test_browser_skill.py` | 15 | Domain allowlist, scheme validation, SSRF checks, XML context defusing |
| `test_research_skill.py` | 14 | Web research sanitization, SSRF IP blocking, source citation formatting |
| `test_voice_pipeline.py` | 14 | LocalFirst STT/TTS abstractions, barge-in logic, wake-word state |
| `test_execution_pipeline.py` | 13 | ExecutionEngine, atomic verifiers, VerifierRegistry |
| `test_agent_task_loop.py` | 13 | Multi-step agent loop, step validation, replanning, failure recovery |
| `test_core_infrastructure.py` | 11 | OliverConfig, RedactedFormatter, structured logging, errors |
| `test_adapter_parity.py` | 6 | Backward compatibility adapters and legacy command routing |
| `test_skill_registry.py` | 5 | Dynamic skill discovery, health checks, lifecycle enable/disable |
| `test_llm_provider.py` | 4 | Ollama REST endpoints, payload generation, fallback resilience |
| **Total** | **252** | **100% Passed (0 Failures, 0 Errors)** |

---

## ⚠️ Troubleshooting & Known Limitations

### 1. "Local AI is offline. Please start Ollama."
- **Cause**: The Ollama background process is not running on `localhost:11434`.
- **Resolution**: Open a terminal and run `ollama serve`. Confirm access by visiting `http://localhost:11434` in your browser.

### 2. Microphone Input Not Detected
- **Cause**: Windows microphone permissions are disabled or PyAudio cannot access the default input device.
- **Resolution**:
  1. Open Windows Settings > Privacy & Security > Microphone and ensure **"Let desktop apps access your microphone"** is ON.
  2. Confirm your recording device is enabled in the Windows Sound Control Panel.

### 3. Missing Vosk Model Warning
- **Cause**: No offline Vosk model was found in cache or project folders.
- **Resolution**: Download [vosk-model-small-en-us-0.15](https://alphacephei.com/vosk/models) and extract it to `~/.cache/vosk/vosk-model-small-en-us-0.15`.

### 4. Hardware Verification Notice
- Automated regression tests verify all software logic headlessly. Live microphone acoustic accuracy, physical speaker output, high-DPI multi-monitor display scaling, and GPU inference latency require manual confirmation on your specific hardware setup (see `docs/WINDOWS_HARDWARE_TEST_CHECKLIST.md`).

---

## 👨‍💻 Author & Attribution

**Ashish Sahoo**
- **GitHub**: [@ashishsahoo18](https://github.com/ashishsahoo18)
- **Project**: OLIVER 2.0 — Windows AI Cockpit

---

## 📄 License

No license has currently been declared for this repository. All rights are reserved by the author.
