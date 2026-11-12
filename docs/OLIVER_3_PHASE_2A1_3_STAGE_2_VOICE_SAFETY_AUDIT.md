# OLIVER 3.0 — Phase 2A.1.3 Stage 2: Voice Reliability & Safety Audit Report

**Date of Audit:** 2026-11-12  
**Environment:** Windows 10, Python 3.13.5, Vosk STT (Offline), Ollama (Llama 3.2), CustomTkinter UI, FastAPI Backend  
**Audit Authorization Mode:** STRICTLY READ-ONLY (No code, config, database, or environment modified)

---

## 1. Executive Summary

This comprehensive audit investigated the five key focus areas of OLIVER's voice processing architecture:
1. **Vosk Transcription Confidence Reliability (P3):** Confirmed that `VoskSTTEngine` incorrectly assigns an artificial confidence score of `1.0` whenever non-empty text lacks word-level confidence tokens in Vosk's JSON output. In addition, the voice listener silently discards all confidence metadata, returning only raw text to callers.
2. **Cockpit Voice Metadata Display (P4):** Confirmed that `ui/chat.py` and `ui/app.py` currently have no access to the recognition confidence, engine identity, or latency, because `VoiceManager.listen_once()` returns a plain `str`. A non-blocking telemetry bridge is needed to display voice metadata in the cockpit.
3. **Accidental Website Opening Protection (P7):** Confirmed that any spoken phrase misrecognized with a period (such as `"open ear-dope.com"` or any phonetic artifact matching `[a-zA-Z0-9-]+\.[a-zA-Z0-9-]+`) is automatically treated as a website and navigated to by Firefox without user confirmation. A confirmation barrier is required for arbitrary domain navigation while preserving convenient shortcuts for recognized aliases.
4. **Dual Wake Phrase Support (P8):** Confirmed that `WakeWordDetector` only supports a single configured wake string (`self.wake_word: str`). It cannot currently monitor both `"Hey OLIVER"` and `"Hello OLIVER"` concurrently.
5. **Performance and Threading:** Confirmed that push-to-talk capture runs on a dedicated worker thread (`threading.Thread` spawned by `_process_command` and `_handle_voice_input`) and posts UI updates to the main thread via `UIEventQueue`, preventing UI freezes.

---

## 2. Current Voice Architecture & Execution Flow

```
+---------------------------------------------------------------------------------------+
| PUSH-TO-TALK FLOW                                                                     |
|                                                                                       |
|  [User Clicks MIC Button]                                                             |
|           |                                                                           |
|           v                                                                           |
|  ui/chat.py: CommandConsolePanel.start_voice_input()                                   |
|           |                                                                           |
|           v (spawns daemon thread)                                                    |
|  ui/chat.py: _handle_voice_input()                                                    |
|           |                                                                           |
|           v                                                                           |
|  voice/voice_manager.py: VoiceManager.listen_once()                                   |
|           |                                                                           |
|           v                                                                           |
|  voice/listener.py: VoiceListener.listen_once()                                       |
|           |                                                                           |
|           +---> AudioCapture.capture_audio() [16kHz, 1024-chunk, PyAudio/sr]           |
|           |                                                                           |
|           +---> LocalFirstSTTEngine.transcribe()                                      |
|           |           |                                                               |
|           |           v                                                               |
|           |     voice/stt/vosk_engine.py: VoskSTTEngine.transcribe()                   |
|           |           |  (runs KaldiRecognizer, parses JSON text & word confs)        |
|           |           v                                                               |
|           |     Returns: TranscriptionResult(text, confidence, engine, latency_s)     |
|           |                                                                           |
|           v                                                                           |
|  VoiceListener._recognize_audio():                                                    |
|     - Drops text if confidence < 0.25                                                 |
|     - STORES result in self.last_result                                               |
|     - RETURNS: result.text.strip()  <--- METADATA TRUNCATED TO PLAIN STR              |
|           |                                                                           |
|           v                                                                           |
|  VoiceManager.listen_once() RETURNS plain str                                         |
|           |                                                                           |
|           v                                                                           |
|  ui/chat.py: receives plain str text                                                  |
|     - Posts text to transcript_var                                                    |
|     - Dispatches text to _process_command(text)                                       |
|           |                                                                           |
|           v                                                                           |
|  ai/assistant.py -> router/router.py -> execution/engine.py                           |
+---------------------------------------------------------------------------------------+
```

---

## 3. Detailed Audit Findings by Focus Area

### 3.1 Audit A: Vosk Confidence Reliability (P3)
**Status:** **CONFIRMED**

#### Exact Source References:
- [`voice/stt/vosk_engine.py:123-135`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/voice/stt/vosk_engine.py#L123-L135)
- [`voice/listener.py:85-94`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/voice/listener.py#L85-L94)
- [`voice/stt/base.py:14-29`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/voice/stt/base.py#L14-L29)

#### Findings:
1. **Misleading Default Confidence in VoskSTTEngine:**
   In `voice/stt/vosk_engine.py`, lines 127–132:
   ```python
   word_list = result_data.get("result", [])
   if word_list and isinstance(word_list, list):
       confs = [float(w.get("conf", 1.0)) for w in word_list if "conf" in w]
       avg_confidence = sum(confs) / len(confs) if confs else (1.0 if text else 0.0)
   else:
       avg_confidence = 1.0 if text else 0.0
   ```
   **Confirmed:** If Vosk outputs a text transcription without word-level confidence entries (e.g. `word_list == []`), or if words omit `"conf"`, `avg_confidence` defaults to `1.0`. A completely uncertain or garbled acoustic guess can receive a perfect `1.0` confidence score.
2. **Metadata Truncation in Listener:**
   In `voice/listener.py`, lines 88–94:
   ```python
   result = self.stt_engine.transcribe(audio, language=self.language)
   self.last_result = result
   if result.confidence < 0.25 and result.text:
       self.logger.warning("STT produced low-confidence transcript (%.2f): '%s'; ignoring", result.confidence, result.text)
       return ""
   return result.text.strip()
   ```
   `listen_once()` returns only `str`. Callers (like `VoiceManager` and the UI) never receive `result.confidence`, `result.engine`, or `result.latency_s`.
3. **Arbitrary Threshold:**
   The `0.25` threshold is hardcoded in `VoiceListener._recognize_audio`. Because uncalibrated transcripts can be assigned `1.0`, this threshold is ineffective at filtering out false positives.

#### Recommended Strategy:
- Differentiate transcription states:
  - `HIGH_CONFIDENCE`: Valid word tokens present, calculated average confidence $\ge$ calibrated threshold (e.g. 0.65).
  - `LOW_CONFIDENCE`: Valid word tokens present, calculated average confidence $<$ calibrated threshold.
  - `CONFIDENCE_UNAVAILABLE`: Valid text produced, but word-level confidences absent from engine output (assign `None` or distinct flag, never `1.0`).
  - `EMPTY_TRANSCRIPT`: No speech detected or blank output (`confidence = 0.0`).
  - `MALFORMED_OUTPUT`: STT engine JSON parsing failed or exception encountered.

---

### 3.2 Audit B: Cockpit Voice Transcription Metadata (P4)
**Status:** **CONFIRMED**

#### Exact Source References:
- [`ui/chat.py:935-964`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/ui/chat.py#L935-L964)
- [`ui/app.py:659-660, 1020-1032`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/ui/app.py#L659-L660)
- [`voice/voice_manager.py:110-158`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/voice/voice_manager.py#L110-L158)

#### Findings:
1. In `ui/app.py` line 659, the cockpit system monitor has telemetry labels:
   - `VOICE` (displays state: `"IDLE"`, `"LISTENING"`, `"SPEAKING"`, `"READY"`)
   - `MIC PRIVACY` (displays `"MIC: OPEN"` or `"MIC: CLOSED"`)
2. There is currently **no display pill or label** for STT engine identity, last confidence score, or transcription latency.
3. In `ui/chat.py`, `_handle_voice_input` only updates `self.transcript_var.set(text)`.
4. `VoiceManager` has property `last_transcription_result`, but it is not polled or pushed to the UI event queue.

#### Recommended Design:
- Update `VoiceManager.listen_once()` or provide `VoiceManager.get_last_result()` to yield structured metadata.
- When `_handle_voice_input()` receives speech, post a thread-safe update to the cockpit panel via `UIEventQueue`:
  - Format: `VOICE | Vosk | Conf: 0.82 | READY` (or `VOICE | Vosk | Conf: N/A | READY` if unavailable).
  - High confidence ($\ge 0.65$): Green indicator (`#10B981`).
  - Medium/Low confidence ($0.40 - 0.65$): Amber indicator (`#F59E0B`).
  - Unconfident/Noise ($< 0.40$): Red indicator (`#EF4444`).
- All updates remain asynchronous via `self.event_bridge.post(...)`, ensuring zero UI thread blocking.

---

### 3.3 Audit C: Accidental Website Opening Protection (P7)
**Status:** **CONFIRMED**

#### Exact Source References:
- [`router/router.py:87-89`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice assistant/router/router.py#L87-L89)
- [`commands/browser.py:209-217`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my own voice assistant/commands/browser.py#L209-L217)
- [`skills/builtin/browser_skill.py:109-115`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my own voice assistant/skills/builtin/browser_skill.py#L109-L115)
- [`security/policy_engine.py:135-144`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my own voice assistant/security/policy_engine.py#L135-L144)

#### Findings:
1. **The Dangerous Bridge in `router/router.py:89`:**
   ```python
   # Universal Website & Service opening in Firefox
   (re.compile(r"^(?:open|go to|visit)\s+(?:the\s+)?(portfolio|...|youtube|...)(?:\s+website|\s+site)?$", re.IGNORECASE), "browser.open_site", "site_name"),
   (re.compile(r"^(?:open|go to|visit)\s+(?:the\s+)?([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+(?:/\S*)?)$", re.IGNORECASE), "browser.open_site", "site_name"),
   ```
   If spoken speech `"open youtube"` is phonetically misrecognized as `"open ear-dope.com"`, rule 89 matches immediately as `browser.open_site` with `site_name="ear-dope.com"`.
2. **Auto-Navigation in `commands/browser.py:215`:**
   ```python
   # Check if the target is already a valid URL or looks like a domain name
   if clean_name.startswith(("http://", "https://")) or ("." in clean_name and " " not in clean_name):
       return self.open_url(clean_name, raw_target)
   ```
   Because `"ear-dope.com"` contains a dot and no spaces, `open_url` is called directly, launching Firefox to open `https://ear-dope.com`.
3. **Zero Policy Gating:**
   `browser.open_site` has `risk_level = ToolRiskLevel.SAFE` (Risk 0). Under `PolicyEngine`, Risk 0 is auto-allowed with no confirmation required.

#### Recommended Safety Proposal:
- **Preserve Whitelisted Shortcuts:** Known aliases in `BrowserCommands.sites` (e.g. `youtube`, `google`, `github`, `portfolio`) remain Risk 0 / auto-allowed.
- **Confirmation Barrier for Arbitrary Domains:**
  When `browser.open_site` receives an arbitrary domain that is not in `BrowserCommands.sites`:
  - If the invocation source is voice (or marked uncertain), trigger `ToolResult(status="NEED_CONFIRM")` requesting explicit user approval.
  - The UI confirmation modal speaks/displays: *"Are you sure you want to navigate to external website 'ear-dope.com'?"*
  - Rejection or cancellation cleanly aborts execution without opening any browser.

---

### 3.4 Audit D: Dual Wake Phrase Support (P8)
**Status:** **CONFIRMED**

#### Exact Source References:
- [`voice/wakeword.py:26, 31, 56-61, 119-135`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my own voice assistant/voice/wakeword.py#L26)
- [`voice/voice_manager.py:57-58, 211-216`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my own voice assistant/voice/voice_manager.py#L57-L58)
- [`core/config.py:59-64`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my own voice assistant/core/config.py#L59-L64)
- [`config/voice_settings.json:9`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my own voice assistant/config/voice_settings.json#L9)

#### Findings:
1. **Single Wake Word Constraint:**
   `WakeWordDetector` in `voice/wakeword.py` stores a single string:
   ```python
   self.wake_word = wake_word.lower().strip()
   ```
   Matching logic in `_contains_wake_word(self, text: str)` only checks:
   ```python
   if self.wake_word in text:
       return True
   if len(wake_words) > 1 and all(w in text for w in wake_words):
       return True
   ```
2. **Current Configuration:**
   - In `core/config.py:59-64`:
     - `wake_word` defaults to `os.getenv("WAKE_WORD", "hey oliver")`
     - `wake_word_alias` defaults to `os.getenv("WAKE_WORD_ALIAS", "hey ashish")`
   - In `config/voice_settings.json`: `"wake_word": "hey Ashish"`
3. **Gap:**
   The user explicitly requires dual wake phrase support:
   1. `"Hey OLIVER"`
   2. `"Hello OLIVER"`
   Currently, if `wake_word` is set to `"hey oliver"`, saying `"hello oliver"` fails because `all(w in text for w in ["hey", "oliver"])` evaluates to `False` (word `"hey"` is missing).

#### Recommended Dual Wake Word Design:
- Support a collection of supported wake phrases in `WakeWordDetector`:
  ```python
  DEFAULT_WAKE_PHRASES = ["hey oliver", "hello oliver"]
  ```
- Support parsing comma-separated phrases from config/env: e.g. `"hey oliver, hello oliver"`.
- Token-matching loop evaluates each valid candidate phrase independently.
- Both phrases trigger the exact same callback and wake state.
- Push-to-talk remains completely independent.

---

### 3.5 Audit E: Performance and Resource Safety
**Status:** **CONFIRMED**

#### Findings:
1. **Thread Isolation:**
   - Push-to-talk recording runs inside a spawned `threading.Thread` (`name="OliverVoiceInputThread"`).
   - Audio transcription does not block the Tkinter main loop.
   - All state updates use `UIEventQueue` thread-safe message posting.
2. **STT Resource Overhead:**
   - Vosk offline model is loaded once into memory upon initial recognition and cached in `VoskSTTEngine._model`. Subsequent calls do not reload Kaldi weights from disk.
   - STT latency is recorded in `TranscriptionResult.latency_s` (typically 0.3s–0.8s on modern multi-core x86_64).
3. **No UI Contention:**
   - Passing metadata (confidence, engine, latency) involves passing small primitives (`float`, `str`) across existing queues, introducing negligible CPU/memory overhead.

---

## 4. Prioritized Stage 2 Implementation Plan

Based on architectural dependencies, the recommended implementation sequence is:

### Stage 2A: Vosk Confidence Reliability (P3)
- **Files to Modify:**
  - `voice/stt/vosk_engine.py`: Fix misleading `1.0` confidence calculation when word-level tokens are absent. Return `confidence=None` or explicit unavailable state when tokens lack scores.
  - `voice/stt/base.py`: Add `confidence_available: bool` property or sentinel to `TranscriptionResult`.
  - `voice/listener.py`: Allow passing structured `TranscriptionResult` or exposing confidence without blind rejection.
- **Tests to Add:**
  - `tests/test_stage2_voice_confidence.py`: Test empty speech, word-level confidence averaging, missing word confidence fallback, threshold boundary checks.

### Stage 2B: Cockpit Voice Metadata Telemetry (P4)
- **Files to Modify:**
  - `voice/voice_manager.py`: Expose structured metadata from last transcription.
  - `ui/chat.py`: In `_handle_voice_input`, post metadata to cockpit event queue.
  - `ui/app.py`: Update System Monitor card to display engine, confidence score, and status.
- **Tests to Add:**
  - Unit tests verifying thread-safe posting of metadata without UI blocking.

### Stage 2C: Safe Arbitrary URL Confirmation (P7)
- **Files to Modify:**
  - `skills/builtin/browser_skill.py`: In `open_site()`, check if `target` is in recognized `BrowserCommands.sites`. If it is an unlisted arbitrary domain, return `ToolResult(status="NEED_CONFIRM", ...)`.
  - `router/router.py`: Ensure known aliases bypass confirmation while arbitrary domain patterns require confirmation when invoked from voice.
- **Tests to Add:**
  - `tests/test_stage2_browser_safety.py`: Test that "open youtube" executes directly, while "open ear-dope.com" triggers `NEED_CONFIRM`.

### Stage 2D: Dual Wake Phrase Support (P8)
- **Files to Modify:**
  - `voice/wakeword.py`: Update `WakeWordDetector` to accept and evaluate multiple wake phrases (`"hey oliver"` and `"hello oliver"`).
  - `core/config.py`: Update configuration defaults to support dual phrases.
- **Tests to Add:**
  - `tests/test_stage2_wakeword.py`: Test positive matches for `"hey oliver"`, `"hello oliver"`, case-insensitivity, and negative matches for unrelated speech.

### Stage 2E: Regression & Acceptance Testing
- Full verification of existing test suites:
  - Focused Stage 1 & 1.1 tests (`21/21`)
  - Browser skill regression (`15/15`)
  - Parity tests (`6/6`)
  - Execution pipeline tests (`13/13`)
  - API client matrix (`15/15`)

---

## 5. Git Status and Safety Baseline

### Git Status (Unchanged throughout audit):
```
 M router/router.py
 M skills/builtin/browser_skill.py
 M ui/app.py
 M ui/chat.py
?? scratch/acc_test_idempotency.py
?? tests/test_api_client.py
?? tests/test_stage1_browser_routing.py
```

### Safety Confirmations:
- **No source code was modified.**
- **No tests were modified.**
- **No databases were accessed, modified, or migrated.**
- **No environment or configuration files (`.env`, `voice_settings.json`) were altered.**
- **No packages were installed or removed.**
- **No external services (Ollama, Docker, FastAPI, PostgreSQL) were started or stopped.**

---

## 6. Stop Condition

In strict accordance with the instructions:
**STOPPING HERE.**  
No implementation of Stage 2 has been performed. Awaiting explicit authorization before starting Stage 2A.

