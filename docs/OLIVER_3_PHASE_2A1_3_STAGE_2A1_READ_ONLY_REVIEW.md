# OLIVER 3.0 — Phase 2A.1.3 Stage 2A.1 Read-Only Implementation Review & Safety Audit

**Date:** November 12, 2026  
**Review Type:** Strictly Read-Only Code Review & Safety Verification  
**Reviewed Artifact:** Stage 2A Implementation (Vosk Confidence Reliability & Structured Transcription Metadata)  
**Readiness Decision:** **CONDITIONAL PASS** (Defect identified in VoiceManager error/disabled branches requiring fix before Stage 2B UI integration)  

---

## 1. Executive Summary

This independent read-only audit inspected the source code, Git changes, caller interfaces, edge cases, and test suites completed during **Phase 2A.1.3 Stage 2A**.

### Key Review Outcomes:
1. **Manufactured `1.0` Confidence Elimination:** **VERIFIED.** Vosk offline engine (`voice/stt/vosk_engine.py`) no longer manufactures `1.0` when word-level confidence tokens are absent. It sets `confidence = None` and `confidence_available = False`.
2. **Sanitization of Floats:** **VERIFIED.** `TranscriptionResult.__post_init__` successfully rejects `NaN`, `+Inf`, `-Inf`, negative numbers, and values exceeding `1.0`.
3. **Structured Preservation & Backward Parity:** **VERIFIED.** `listen_once_result()` returns structured `TranscriptionResult`, while `listen_once()` returns a clean `str` across all callers.
4. **Automated Test Parity:** **VERIFIED.** 90 of 90 tests pass across the test suite.
5. **Defects Identified:**
   - **Defect A (High Severity / Runtime Failure in Non-Happy Paths):** In `voice/voice_manager.py` (lines 121, 128, 170), `listen_once_result()` attempts to instantiate `TranscriptionResult(..., is_final=True, ...)`. However, `TranscriptionResult` in `voice/stt/base.py` **does not have an `is_final` field**. As a consequence, if voice is disabled (`voice_enabled=False`), if listening is already active (`busy`), or if an unhandled exception occurs during listening, Python raises `TypeError: TranscriptionResult.__init__() got an unexpected keyword argument 'is_final'`.
   - **Defect B (Medium Severity / Defensive Coercion Gap):** In Python, `isinstance(True, int)` is `True`, and `float(True)` evaluates to `1.0` (similarly `float(False)` evaluates to `0.0`). Neither `base.py` nor `vosk_engine.py` explicitly tests `not isinstance(conf, bool)`. Consequently, passing boolean confidence values coerces them to `1.0` or `0.0` instead of rejecting them.

---

## 2. Git Baseline and Final Status

Command: `git status --short`
```
 M router/router.py
 M skills/builtin/browser_skill.py
 M ui/app.py
 M ui/chat.py
 M voice/listener.py
 M voice/stt/base.py
 M voice/stt/vosk_engine.py
 M voice/voice_manager.py
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2A1_READ_ONLY_REVIEW.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2A_VOSK_CONFIDENCE_REPORT.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2_VOICE_SAFETY_AUDIT.md
?? scratch/acc_test_idempotency.py
?? tests/test_api_client.py
?? tests/test_stage1_browser_routing.py
?? tests/test_stage2a_vosk_confidence.py
```

- **Branch:** `main` (up to date with `origin/main`).
- **Safety Boundary Adherence:** Zero staged commits, zero branch switches, zero deletions of untracked user files, zero changes to configuration, `.env`, or database files (`database/oliver.db`, WAL, SHM).

---

## 3. Stage 2A Modified-File Inventory

| File | Changes Made in Stage 2A | Audit Assessment |
|---|---|---|
| `voice/stt/base.py` | Added `confidence_available: bool = True`, updated `confidence: Optional[float] = None`, added `__post_init__` sanitization. | Clean, non-breaking dataclass extension. |
| `voice/stt/vosk_engine.py` | Refactored `_parse_vosk_result()` and `_parse_vosk_dict()`, eliminated fallback `1.0`, aggregated word confidences as arithmetic mean, safe JSON decoding. | Deterministic and robust. Missing explicit `bool` check. |
| `voice/listener.py` | Added `listen_once_result() -> TranscriptionResult`, wrapped `listen_once() -> str`, checked `confidence_available` before filtering `<0.25`. | 100% backward-compatible plain string wrapper. |
| `voice/voice_manager.py` | Added `last_transcription_result`, added `listen_once_result()`, updated `listen_once()`. | **Defect A found:** invalid `is_final=True` kwarg on lines 121, 128, 170. |

---

## 4. Confidence Calculation Review (`voice/stt/vosk_engine.py`)

Inspection of `VoskSTTEngine._parse_vosk_dict`:
1. **Fallback `1.0` Elimination:** Confirmed removed. When `result_data` lacks word tokens or `"conf"` keys, `avg_confidence` remains `None` and `confidence_available = False`.
2. **Empty Text Handling:** When `text == ""`, sets `avg_confidence = 0.0` and `confidence_available = True`.
3. **Valid Word Confidences:** When `valid_confs` contains floats in `[0.0, 1.0]`, calculates `sum(valid_confs) / len(valid_confs)`.
4. **Malformed JSON:** Confirmed caught by `try ... json.loads(...) except Exception as json_err:`, returning safe empty `TranscriptionResult` with `details={"error": ..., "raw": ...}`.

---

## 5. Confidence Sanitization Review (`voice/stt/base.py`)

Inspection of `TranscriptionResult.__post_init__`:
```python
    def __post_init__(self) -> None:
        """Sanitize and validate confidence score."""
        if not self.confidence_available or self.confidence is None:
            self.confidence = None
            self.confidence_available = False
            return

        try:
            import math
            conf = float(self.confidence)
            if math.isnan(conf) or math.isinf(conf) or conf < 0.0 or conf > 1.0:
                self.confidence = None
                self.confidence_available = False
            else:
                self.confidence = conf
                self.confidence_available = True
        except (ValueError, TypeError):
            self.confidence = None
            self.confidence_available = False
```

### Self-Consistency Check:
- If `confidence_available is False`: automatically sets `confidence = None`. Contradictory states (`confidence=0.8, available=False`) cannot persist.
- If `confidence is None`: automatically sets `confidence_available = False`. Contradictory states (`confidence=None, available=True`) cannot persist.
- If `confidence` is non-numeric, NaN, infinite, or out of range: sanitized to `confidence=None, confidence_available=False`.

---

## 6. Boolean, NaN, Infinity, and Out-of-Range Validation Findings

Empirically verified through Python runtime evaluation:

| Test Input | `TranscriptionResult` Output | `_parse_vosk_dict` Output | Evaluation |
|---|---|---|---|
| `float('nan')` | `conf=None, avail=False` | `conf=None, avail=False` | **PASSED** (Rejected safely) |
| `float('inf')` | `conf=None, avail=False` | `conf=None, avail=False` | **PASSED** (Rejected safely) |
| `float('-inf')` | `conf=None, avail=False` | `conf=None, avail=False` | **PASSED** (Rejected safely) |
| `-0.5` | `conf=None, avail=False` | `conf=None, avail=False` | **PASSED** (Rejected safely) |
| `1.5` | `conf=None, avail=False` | `conf=None, avail=False` | **PASSED** (Rejected safely) |
| `"abc"` | `conf=None, avail=False` | `conf=None, avail=False` | **PASSED** (Rejected safely) |
| `None` | `conf=None, avail=False` | `conf=None, avail=False` | **PASSED** (Rejected safely) |
| `True` | `conf=1.0, avail=True` | `conf=1.0, avail=True` | **DEFECT B:** Coerced to float `1.0` (not rejected) |
| `False` | `conf=0.0, avail=True` | `conf=0.0, avail=True` | **DEFECT B:** Coerced to float `0.0` (not rejected) |

**Root Cause for Defect B:** In Python, `isinstance(True, int)` is true, so `float(True) == 1.0`. Neither `isinstance(w["conf"], bool)` nor `isinstance(self.confidence, bool)` is checked before converting to `float`. In native Vosk Kaldi output, booleans are never emitted, but defensive type-safety is incomplete.

---

## 7. Mixed Word-Confidence Aggregation Findings

The current aggregation policy in `_parse_vosk_dict`:
```python
valid_confs = [float(w["conf"]) for w in word_list if valid]
if valid_confs:
    avg_confidence = sum(valid_confs) / len(valid_confs)
```

### Analysis:
- **All words valid:** Arithmetic mean over all words.
- **Some words valid, some missing/invalid:** Average is calculated over `len(valid_confs)`.
  *Limitation:* If a 5-word sentence has only 1 word with `conf=0.80` and 4 words with missing confidence, the result claims `0.80` confidence rather than penalizing for the missing 80% of tokens.
  *Real-world context:* In Vosk offline Kaldi recognizer, the recognizer either populates `"conf"` for all recognized words or emits no word tokens at all. Partial presence does not occur in standard Kaldi JSON.

---

## 8. Structured Transcription Preservation Review

- `VoiceListener.listen_once_result()` captures audio, passes it to STT engine, stores `self.last_result = result`, and returns the structured `TranscriptionResult`.
- `VoiceListener.listen_once()` calls `listen_once_result()`, applies `<0.25` filtering only if confidence is available, and returns `result.text.strip()`.
- `VoiceManager.listen_once_result()` triggers safe barge-in, manages `LISTENING`/`PROCESSING`/`READY`/`ERROR` state machine transitions, records `self.last_transcription_result = result`, and returns the structured object.
- `VoiceManager.listen_once()` calls `listen_once_result()` and returns `result.text.strip()`.

---

## 9. Backward Compatibility Review

Complete codebase caller audit:
1. `ui/chat.py` (line 947):
   ```python
   text = self.voice_manager.listen_once(status_callback=on_status)
   ```
   Expects `str`. Receives `str`. **100% backward compatible.**
2. `voice/voice_manager.py` (line 181 — `confirm_action_by_voice`):
   ```python
   spoken_text = self.listen_once(timeout=timeout, phrase_time_limit=4)
   ```
   Expects `str`. Receives `str`. **100% backward compatible.**
3. `tests/regression/test_voice_pipeline.py`:
   Calls `listener.listen_once(...)` and `vm.listen_once(...)`. Both receive `str`. **100% backward compatible.**

---

## 10. Low-Confidence Filtering Review (`<0.25`)

Line 109 of `voice/listener.py`:
```python
if result.confidence_available and result.confidence is not None:
    if result.confidence < 0.25 and result.text:
        self.logger.warning("STT produced low-confidence transcript (%.2f): '%s'; ignoring", result.confidence, result.text)
        return ""
```

- When confidence is `None` (`confidence_available=False`): The filter is bypassed. Valid text is preserved.
- When confidence is `< 0.25`: Empty string `""` is returned.
- No new universal threshold was introduced. The existing OLIVER 2.0 threshold (`0.25`) was preserved safely.

---

## 11. Existing Caller Inventory

| Caller Location | Method Called | Return Type Received | Compatibility Status |
|---|---|---|---|
| `ui/chat.py:947` | `VoiceManager.listen_once()` | `str` | Compatible (happy path); crashes on Defect A |
| `voice/voice_manager.py:181` | `VoiceManager.listen_once()` | `str` | Compatible (happy path); crashes on Defect A |
| `voice/listener.py:101` | `VoiceListener.listen_once_result()` | `TranscriptionResult` | Compatible |
| `voice/voice_manager.py:148` | `VoiceListener.listen_once_result()` | `TranscriptionResult` | Compatible |
| `voice/voice_manager.py:189` | `VoiceManager.listen_once_result()` | `TranscriptionResult` | Compatible |
| `tests/regression/test_voice_pipeline.py:133` | `VoiceListener.listen_once()` | `str` | Compatible |
| `tests/regression/test_voice_pipeline.py:173` | `VoiceManager.listen_once()` | `str` | Compatible |

---

## 12. Test Source Inspection (`tests/test_stage2a_vosk_confidence.py`)

The test suite contains 21 distinct tests across 3 classes:
1. `TestVoskConfidenceScenarios`: 10 tests for confidence calculation and sanitization.
2. `TestStructuredResultPreservation`: 7 tests for metadata preservation and backward compatibility.
3. `TestVoicePipelineIntegration`: 4 tests for listener threshold filtering, sanitization bounds, and manager integration.

**Observation on Test Coverage Gap:**
In `test_voice_manager_listen_once_result_and_backward_compat`, `vm.listener.listen_once_result` was mocked to return a valid result. The test never exercised:
- `voice_enabled == False`
- `_is_listening == True` (busy lock)
- `listener.listen_once_result` throwing an exception (error state)
Because none of those three error branches were tested, the `is_final=True` `TypeError` went undetected during the Stage 2A test run.

---

## 13. Actual Test Execution Results

All commands were executed independently during this review:

| # | Test Group / Command | Passed | Total | Elapsed | Result |
|---|---|---:|---:|---:|---|
| 1 | `pytest tests/test_stage2a_vosk_confidence.py -v` | 21 | 21 | 1.12s | **PASSED** |
| 2 | `pytest tests/test_stage1_browser_routing.py -q` | 21 | 21 | 4.68s | **PASSED** |
| 3 | `pytest tests/regression/test_browser_skill.py -q` | 15 | 15 | 1.56s | **PASSED** |
| 4 | `pytest tests/regression/test_adapter_parity.py -q` | 6 | 6 | 2.47s | **PASSED** |
| 5 | `pytest tests/regression/test_execution_pipeline.py -q` | 13 | 13 | 3.28s | **PASSED** |
| 6 | `python -m unittest tests/regression/test_voice_pipeline.py` | 14 | 14 | 1.98s | **PASSED** |
| **TOTAL** | | **90** | **90** | **15.09s** | **100% PASS** |

---

## 14. Database and Configuration Safety Verification

- `database/oliver.db`: Untouched. File size and timestamp unmodified.
- `database/oliver.db-wal` / `-shm`: Not recreated or touched.
- `config/voice_settings.json`: Preserved.
- `.env`: Preserved.
- Dependencies: Zero package installations or dependency modifications.

---

## 15. Identified Defects and Risks

### Defect A (CRITICAL / Runtime Crash in Error & Disabled Paths)
- **Location:** `voice/voice_manager.py`, lines 121, 128, 170.
- **Code:**
  ```python
  # Line 121:
  res = TranscriptionResult(text="", confidence=0.0, is_final=True, engine="disabled", confidence_available=True)
  # Line 128:
  res = TranscriptionResult(text="", confidence=0.0, is_final=True, engine="busy", confidence_available=True)
  # Line 170:
  res = TranscriptionResult(text="", confidence=0.0, is_final=True, engine="error", details={"error": str(exc)}, confidence_available=True)
  ```
- **Root Cause:** `is_final` is not a field of `TranscriptionResult` in `voice/stt/base.py`.
- **Runtime Impact:**
  Calling `vm.listen_once_result()` or `vm.listen_once()` when voice is disabled, when busy, or when an exception occurs crashes with:
  `TypeError: TranscriptionResult.__init__() got an unexpected keyword argument 'is_final'`
- **Required Resolution:** Remove `is_final=True` from all 3 instantiations in `voice/voice_manager.py`.

### Defect B (MEDIUM / Defensive Boolean Coercion)
- **Location:** `voice/stt/base.py` (`__post_init__`) and `voice/stt/vosk_engine.py` (`_parse_vosk_dict`).
- **Code:** `float(True)` evaluates to `1.0`; `float(False)` evaluates to `0.0`.
- **Root Cause:** Python booleans inherit from `int`. Neither module checks `if isinstance(val, bool):`.
- **Runtime Impact:** Non-fatal for Vosk (Kaldi returns JSON floats), but fails strict defensive typing if boolean values are injected.
- **Required Resolution:** Add `if isinstance(conf, bool): self.confidence = None; self.confidence_available = False` to `TranscriptionResult.__post_init__` and `if isinstance(w["conf"], bool): continue` in `vosk_engine.py`.

---

## 16. Real Microphone Manual Testing Limitations

1. **Hardware vs. Synthetic Audio:** All 21 tests in `tests/test_stage2a_vosk_confidence.py` utilize synthetic JSON strings or mock objects. None stream raw PCM from an actual USB/audio jack microphone.
2. **Acoustic Variability:** Real speech recognition through Vosk exhibits variable lattice confidence based on microphone gain, background room noise, speech cadence, and model dictionary coverage.
3. **Driver & PyAudio Latency:** Mocked tests do not test PyAudio/SpeechRecognition hardware buffer overruns, timeout exceptions, or device disconnection during active capture.

---

## 17. Final Readiness Decision

### **CONDITIONAL PASS**

**Justification:**
1. The primary architectural objective of Stage 2A — eliminating manufactured `1.0` confidence, establishing `TranscriptionResult` metadata preservation, and maintaining backward-compatible plain string return types — has been implemented and passes all 90 regression tests.
2. However, **Defect A** (`is_final=True` in `voice/voice_manager.py`) is a real runtime defect that will crash the application whenever voice listening is disabled, busy, or encounters a hardware error.
3. **Stage 2B (Cockpit UI Metadata Display) must NOT proceed** until Defect A is resolved.

---

## 18. Recommendations for Next Action

1. Authorize a minimal patch to remove `is_final=True` from lines 121, 128, and 170 of `voice/voice_manager.py`, and add `not isinstance(..., bool)` sanitization in `base.py` and `vosk_engine.py`.
2. Add unit tests for `VoiceManager.listen_once_result()` covering `voice_enabled=False`, busy state, and listener error states.
3. Re-run test suite (target: 24/24 passing).
4. After verification, proceed to Stage 2B.

