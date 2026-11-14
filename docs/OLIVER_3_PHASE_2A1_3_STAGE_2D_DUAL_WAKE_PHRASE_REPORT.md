# OLIVER 3.0 — Phase 2A.1.3 Stage 2D: Dual Wake Phrase Support Report

## 1. Executive Summary

Stage 2D implements **Dual Wake Phrase Support** for OLIVER 3.0, enabling the system to reliably recognize both:
- **"Hey OLIVER"**
- **"Hello OLIVER"**

Both phrases activate the identical wake-word workflow, respecting case insensitivity, whitespace normalization, strict contiguous token matching to prevent false positives, debounce cooldown to prevent duplicate activations, structured transcription metadata preservation, and Stage 2A Vosk confidence filtering (0.25 threshold).

All 22 Stage 2D tests passed (`22/22`). Full regression test suites across all prior stages (Stage 2C URL confirmation, Stage 2B telemetry, Stage 2A Vosk confidence, Stage 1 browser routing, browser skill, adapter parity, execution pipeline, voice pipeline) passed 100% without regression (`164/164 tests passed`).

Neither Stage 2E nor Phase 2.1 was implemented.

---

## 2. Preflight Git Inventory

### Status at Start of Stage 2D
- **Branch:** `main`
- **HEAD Commit:** `e4fbdd1` ("Added something in details")
- **Pre-existing unstaged modifications:**
  - `commands/browser.py` (Stage 2C)
  - `ui/chat.py` (Stage 2B & Stage 2C)
  - `voice/voice_manager.py` (Stage 2B)
- **Pre-existing untracked files:**
  - `browser/url_trust.py` (Stage 2C)
  - `docs/OLIVER_3_PHASE_2A1_3_STAGE_2B_COCKPIT_TELEMETRY_REPORT.md` (Stage 2B)
  - `docs/OLIVER_3_PHASE_2A1_3_STAGE_2B_FINAL_READINESS_AUDIT.md` (Stage 2B)
  - `docs/OLIVER_3_PHASE_2A1_3_STAGE_2C_FINAL_READINESS_AUDIT.md` (Stage 2C)
  - `docs/OLIVER_3_PHASE_2A1_3_STAGE_2C_URL_CONFIRMATION_REPORT.md` (Stage 2C)
  - `tests/test_stage2b_cockpit_telemetry.py` (Stage 2B)
  - `tests/test_stage2c_url_confirmation.py` (Stage 2C)
  - `ui/telemetry_utils.py` (Stage 2B)

### Post-Implementation Working Tree
```
 M commands/browser.py
 M config/voice_settings.json
 M core/config.py
 M ui/chat.py
 M voice/voice_manager.py
 M voice/wakeword.py
?? browser/url_trust.py
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2B_COCKPIT_TELEMETRY_REPORT.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2B_FINAL_READINESS_AUDIT.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2C_FINAL_READINESS_AUDIT.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2C_URL_CONFIRMATION_REPORT.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2D_DUAL_WAKE_PHRASE_REPORT.md
?? tests/test_stage2b_cockpit_telemetry.py
?? tests/test_stage2c_url_confirmation.py
?? tests/test_stage2d_dual_wake_phrases.py
?? ui/telemetry_utils.py
```
Zero files were deleted, reset, or committed.

---

## 3. Existing Wake-Word Architecture

Prior to Stage 2D, `WakeWordDetector` in `voice/wakeword.py` operated on a single string `self.wake_word = "hey oliver"`. Its matching logic (`all(w in text for w in wake_words)`) suffered from false positive vulnerabilities when wake words were scattered across sentences (e.g., `"hey friend what is oliver doing"`) or reversed (`"oliver hey"`). Furthermore, it discarded structured transcription metadata (`TranscriptionResult`) and did not enforce the Stage 2A Vosk 0.25 confidence threshold on wake capture.

---

## 4. Files Changed

### 1. `voice/wakeword.py` (Modified)
- **Dual Wake Phrase Support:** Added `DEFAULT_WAKE_PHRASES = ("hey oliver", "hello oliver")`.
- **Normalization:** Added `normalize_wake_phrase(phrase: str) -> str` to lowercase, strip punctuation, and collapse whitespace.
- **Detector Class Enhancements:**
  - Added `wake_phrases: list[str]` storing configured normalized phrases.
  - Added `wake_word` getter/setter property for full backward compatibility.
  - Added `set_wake_phrases(phrases)` accepting iterables or comma-separated strings with safe fallback.
  - Added `set_wake_word(word)` updating and prepending the primary wake word.
- **Contiguous Token Sequence Matching:**
  - Replaced naive substring / set matching with exact contiguous token sequence comparison.
  - Tokenizes input text by replacing non-word characters with spaces and splitting on whitespace.
  - Iterates over configured wake phrases and checks if phrase tokens match any window of the transcribed tokens.
  - Completely eliminates false positives from scattered words (`"hello to my friend oliver"` -> False) and reversed order (`"oliver hello"` -> False).
- **Debounce Cooldown:**
  - Enforces `self._cooldown_seconds = 2.0` (configurable), blocking duplicate callbacks from a single spoken phrase or subsequent partial speech chunks.
- **Structured Transcription & Confidence Preservation:**
  - Added `_listen_for_short_phrase_result() -> TranscriptionResult`, preserving structured metadata (`engine`, `confidence`, `confidence_available`, `latency_s`) in `self.last_transcription_result`.
  - In `_listen_for_short_phrase()`, applies the Stage 2A confidence check: if genuine confidence is available and `< 0.25`, the transcript is ignored. If confidence is unavailable, it is never filtered.
- **Thread Synchronization:**
  - Added `self._lock = threading.Lock()` around wake phrases access and updates to ensure thread safety under concurrent reader/writer calls.

### 2. `voice/voice_manager.py` (Modified)
- Passed `wake_phrases` setting from configuration into `WakeWordDetector`.
- Added `wake_phrases` property returning currently active wake phrases.
- Added `set_wake_phrases()` allowing dynamic multi-phrase reconfiguration.
- Updated `set_wake_word()` to keep `wake_phrases` and `wake_word` synchronized.
- Updated `_default_settings()` to include `"wake_phrases": ["hey oliver", "hello oliver"]`.
- Updated `_apply_runtime_settings()` to load dual phrases from configuration with fallback.

### 3. `core/config.py` (Modified)
- Updated `VoiceSettings`:
  - `wake_word_alias`: Defaulted to `"hello oliver"` (from legacy `"hey ashish"`).
  - `wake_phrases`: Added field defaulting to `["hey oliver", "hello oliver"]` from `WAKE_PHRASES` env var or defaults.

### 4. `config/voice_settings.json` (Modified)
- Updated user voice configuration JSON to include `"wake_phrases": ["hey oliver", "hello oliver"]` and `"wake_word": "hey oliver"`.

### 5. `tests/test_stage2d_dual_wake_phrases.py` (New File)
- 22 dedicated automated tests covering all required functional, security, configuration, and integration areas.

---

## 5. Dual Phrase Implementation Details

### Contiguous Token Matching Algorithm

```python
def _contains_wake_word(self, text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False

    with self._lock:
        phrases_to_check = list(self.wake_phrases)

    clean_input = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    tokens = clean_input.split()
    if not tokens:
        return False

    for phrase in phrases_to_check:
        phrase_tokens = phrase.split()
        phrase_len = len(phrase_tokens)
        if phrase_len == 0 or len(tokens) < phrase_len:
            continue

        for i in range(len(tokens) - phrase_len + 1):
            if tokens[i : i + phrase_len] == phrase_tokens:
                return True

    return False
```

### Safety and Rejection Verification

| Spoken Phrase | Expected Result | Reason |
|---|:---:|---|
| `"Hey OLIVER"` | MATCH | Exact match for primary wake phrase |
| `"Hello OLIVER"` | MATCH | Exact match for dual wake phrase |
| `"hey   oliver"` | MATCH | Collapses internal whitespace |
| `"hello oliver what time is it"` | MATCH | Wake phrase followed by command |
| `"um hey oliver"` | MATCH | Wake phrase preceded by conversational filler |
| `"oliver"` | NO MATCH | Partial name alone rejected |
| `"hey"` | NO MATCH | Greeting keyword alone rejected |
| `"hello"` | NO MATCH | Greeting keyword alone rejected |
| `"oliver hey"` | NO MATCH | Reversed word order rejected |
| `"oliver hello"` | NO MATCH | Reversed word order rejected |
| `"hey friend what is oliver doing"` | NO MATCH | Scattered non-contiguous keywords rejected |
| `"the olive tree"` | NO MATCH | Substring token mismatch ("olive" != "oliver") |
| `""` (empty) | NO MATCH | Empty/whitespace input rejected |

---

## 6. Confidence Metadata and Pipeline Compatibility

1. **Stage 2A Integration:**
   - When Vosk supplies genuine confidence, `_listen_for_short_phrase()` evaluates `confidence >= 0.25`. Low-confidence transcripts (< 0.25) are logged and discarded.
   - When confidence is unavailable (`confidence_available=False` or `confidence=None`), transcripts are NOT discarded, preventing false rejections on fallback engines.
2. **Push-To-Talk Compatibility:**
   - Push-to-talk invokes `VoiceManager.listen_once()` directly without invoking or colliding with the wake detector.
3. **Emergency Stop (Barge-in):**
   - Invoking `VoiceManager.stop_speaking()` immediately aborts active speech synthesis (`speaker.barge_in()`) without terminating the background wake-word listener thread.

---

## 7. Automated Test Results

All 22 tests in `tests/test_stage2d_dual_wake_phrases.py` passed:

| # | Area / Test Name | Status |
|---|------------------|--------|
| 1 | "Hey OLIVER" recognition (`test_01_hey_oliver_recognition`) | PASSED |
| 2 | "Hello OLIVER" recognition (`test_02_hello_oliver_recognition`) | PASSED |
| 3 | Case-insensitive matching (`test_03_case_insensitive_matching`) | PASSED |
| 4 | Whitespace normalization (`test_04_whitespace_normalization`) | PASSED |
| 5 | Unrelated speech rejection (`test_05_unrelated_speech_rejection`) | PASSED |
| 6 | Partial phrase rejection (`test_06_partial_phrase_rejection`) | PASSED |
| 7 | Ambiguous phrase handling (`test_07_ambiguous_phrase_handling`) | PASSED |
| 8 | Duplicate activation prevention (`test_08_duplicate_activation_prevention`) | PASSED |
| 9 | Both phrases using same activation workflow (`test_09_both_phrases_use_same_activation_workflow`) | PASSED |
| 10 | Configuration loading (`test_10_configuration_loading`) | PASSED |
| 11 | Missing configuration behavior (`test_11_missing_configuration_behavior`) | PASSED |
| 12 | Malformed configuration behavior (`test_12_malformed_configuration_behavior`) | PASSED |
| 13 | Vosk structured transcription compatibility (`test_13_vosk_structured_transcription_compatibility`) | PASSED |
| 14 | Genuine confidence handling (`test_14_genuine_confidence_handling`) | PASSED |
| 15 | Missing confidence handling (`test_15_missing_confidence_handling`) | PASSED |
| 16 | Existing 0.25 threshold compatibility (`test_16_confidence_below_point_25_ignored`) | PASSED |
| 17 | Legacy string API compatibility (`test_17_legacy_string_api_compatibility`) | PASSED |
| 18 | Push-to-talk compatibility (`test_18_push_to_talk_compatibility`) | PASSED |
| 19 | Listener lifecycle safety (`test_19_listener_lifecycle_safety`) | PASSED |
| 20 | VoiceManager integration (`test_20_voice_manager_integration`) | PASSED |
| 21 | Thread-safety regression (`test_21_thread_safety_concurrent_access`) | PASSED |
| 22 | Existing emergency stop compatibility (`test_22_emergency_stop_compatibility`) | PASSED |

---

## 8. Full Regression Test Verification

Each suite was executed in an isolated process to prevent pyttsx3 COM / threading cross-contamination:

```
1. Stage 2D Dual Wake Phrases:
   Command: python -m pytest tests/test_stage2d_dual_wake_phrases.py -v
   Result:  22 passed in 2.89s ...................... [PASSED]

2. Stage 2C URL Confirmation:
   Command: python -m pytest tests/test_stage2c_url_confirmation.py
   Result:  29 passed in 7.23s ............................. [PASSED]

3. Stage 2B Telemetry HUD:
   Command: python -m pytest tests/test_stage2b_cockpit_telemetry.py
   Result:  17 passed in 7.75s ................. [PASSED]

4. Stage 2A Vosk Confidence:
   Command: python -m pytest tests/test_stage2a_vosk_confidence.py
   Result:  27 passed in 0.80s ........................... [PASSED]

5. Stage 1 Browser Routing:
   Command: python -m pytest tests/test_stage1_browser_routing.py
   Result:  21 passed in 4.50s ..................... [PASSED]

6. Browser Skill Regression:
   Command: python -m pytest tests/regression/test_browser_skill.py
   Result:  15 passed in 2.69s ............... [PASSED]

7. Adapter Parity Regression:
   Command: python -m pytest tests/regression/test_adapter_parity.py
   Result:  6 passed in 3.01s ...... [PASSED]

8. Execution Pipeline Regression:
   Command: python -m pytest tests/regression/test_execution_pipeline.py
   Result:  13 passed in 6.59s ............. [PASSED]

9. Voice Pipeline Regression:
   Command: python -m unittest tests/regression/test_voice_pipeline.py
   Result:  Ran 14 tests in 7.863s ... OK [PASSED]

========================================================================================
TOTAL: 164 passed out of 164 tests (100% Pass Rate across all 9 test suites)
========================================================================================
```

---

## 9. Mocked vs Real Hardware Testing

- **Mocked Testing:** All automated tests in `tests/test_stage2d_dual_wake_phrases.py` use simulated audio captures and mocked STT engines. This guarantees deterministic, fast execution without requiring microphone access.
- **Physical Hardware Testing:** Real microphone continuous background listening and physical audio capture were not executed as part of automated CI test runs. Real acoustic environment testing (e.g. ambient noise, acoustic room reflections) is recommended for manual testing in production deployment.

---

## 10. Remaining Limitations

1. **Acoustic Phonetic Ambiguity in Vosk:**
   - Offline Vosk acoustic models may occasionally transcribe "Hey OLIVER" as "a oliver" or "pay oliver" under low signal-to-noise ratio conditions. Stage 2D enforces strict contiguous token matching for "hey oliver" and "hello oliver" to eliminate false positives; under noisy conditions, speaking clearly into the microphone is necessary.
2. **Debounce Interval:**
   - The default cooldown is 2.0 seconds. Rapidly speaking "Hey OLIVER" twice within 2.0 seconds will trigger the assistant once, which is intentional to prevent duplicate sessions.

---

## 11. Scope Boundaries & Certification

- **Stage 2D Scope:** Dual wake phrase support ("Hey OLIVER" and "Hello OLIVER") successfully implemented and verified.
- **Stage 2E (Wake Word Verification & Refinement):** NOT IMPLEMENTED.
- **Phase 2.1 (PostgreSQL Migration):** NOT IMPLEMENTED.
- **Database Status:** Unmodified.
- **Git Actions:** Zero staging, committing, or branch manipulation performed.

