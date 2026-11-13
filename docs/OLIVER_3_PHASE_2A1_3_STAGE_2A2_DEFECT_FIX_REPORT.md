# OLIVER 3.0 — Phase 2A.1.3 Stage 2A.2 Defect Correction & Regression Verification Report

**Date:** November 12, 2026  
**Implementation Scope:** Stage 2A.2 Defect Corrections (Defect A and Defect B only)  
**Readiness Status:** **PASS** — Defect A and Defect B resolved, 96/96 automated tests passing  
**Next Stage:** Stage 2B (Cockpit UI Metadata Display) — NOT AUTHORIZED / Awaiting Explicit Approval  

---

## 1. Executive Summary

Following the **Phase 2A.1.3 Stage 2A.1 Read-Only Review**, two specific defects were authorized for correction:
1. **Defect A (High Severity / Runtime Construction Crash):** In `voice/voice_manager.py`, `listen_once_result()` passed `is_final=True` to `TranscriptionResult`, raising `TypeError` whenever voice was disabled, busy, or encountered a listener exception.
2. **Defect B (Medium Severity / Defensive Boolean Coercion):** Python booleans (`True`, `False`) inherit from `int`, causing `float(True) == 1.0` and `float(False) == 0.0`. Neither `voice/stt/base.py` nor `voice/stt/vosk_engine.py` explicitly rejected `bool` values before numeric conversion.

Both defects have been corrected using minimal, surgical modifications. Double-layer defense-in-depth has been established for boolean sanitization. All 3 non-happy path branches in `VoiceManager` now return valid structured `TranscriptionResult` objects without crashing, and legacy `listen_once()` continues to return plain strings.

A total of **96 automated tests** (27 Stage 2A confidence tests, 21 Stage 1 browser routing tests, 15 browser skill tests, 6 adapter parity tests, 13 execution pipeline tests, and 14 voice pipeline tests) were executed and passed with **100% success**.

---

## 2. Preflight Git Status

Before making changes:
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
All untracked reports and user changes were preserved without overwriting or staging.

---

## 3. Defect A — Root Cause & Resolution

### Root Cause
`TranscriptionResult` is defined in `voice/stt/base.py` with fields:
- `text: str`
- `confidence: Optional[float] = None`
- `engine: str = "unknown"`
- `is_offline: bool = True`
- `latency_s: float = 0.0`
- `external_service_disclosed: bool = False`
- `confidence_available: bool = True`
- `details: dict[str, Any]`

The dataclass does not define an `is_final` field. In `voice/voice_manager.py`, three non-happy path instantiations in `listen_once_result()` included `is_final=True`:
- Line 121 (`voice_enabled == False`)
- Line 128 (`_is_listening == True` duplicate session / busy)
- Line 170 (`except Exception as exc:`)

Calling `listen_once_result()` or `listen_once()` under any of these conditions raised:
`TypeError: TranscriptionResult.__init__() got an unexpected keyword argument 'is_final'`

### Correction Details
In `voice/voice_manager.py`:
- Line 121: Replaced with `TranscriptionResult(text="", confidence=0.0, engine="disabled", confidence_available=True)`.
- Line 128: Replaced with `TranscriptionResult(text="", confidence=0.0, engine="busy", confidence_available=True)`.
- Line 166-173: Replaced with:
  ```python
  res = TranscriptionResult(
      text="",
      confidence=0.0,
      engine="error",
      details={"error": str(exc)},
      confidence_available=True,
  )
  ```
- Result: All branches construct valid `TranscriptionResult` objects. `self.last_transcription_result` is recorded accurately. `listen_once()` returns `""` cleanly without throwing unhandled exceptions.

---

## 4. Defect B — Root Cause & Resolution

### Root Cause
In Python, `bool` is a subclass of `int` (`issubclass(bool, int) is True`). Consequently:
- `float(True)` evaluates to `1.0`.
- `float(False)` evaluates to `0.0`.
- `0.0 <= 1.0 <= 1.0` evaluates to `True`.

Neither `voice/stt/base.py` nor `voice/stt/vosk_engine.py` checked `isinstance(..., bool)` prior to `float(...)`. An injected boolean confidence value was coerced into `1.0` or `0.0` and marked `confidence_available = True`.

### Correction Details
1. **`voice/stt/base.py` (`TranscriptionResult.__post_init__`):**
   Added `isinstance(self.confidence, bool)` to the early exit guard:
   ```python
   if not self.confidence_available or self.confidence is None or isinstance(self.confidence, bool):
       self.confidence = None
       self.confidence_available = False
       return
   ```
2. **`voice/stt/vosk_engine.py` (`VoskSTTEngine._parse_vosk_dict`):**
   Added explicit boolean check before numeric conversion:
   ```python
   raw_conf = w["conf"]
   if isinstance(raw_conf, bool):
       self.logger.warning("Vosk word confidence is boolean; rejecting: %s", raw_conf)
       continue
   ```
3. Result: Booleans (`True`, `False`) are rejected. If all words contain booleans or missing scores, `confidence` is `None` and `confidence_available = False`. Recognized text is safely preserved. Genuine numeric values (`0.0`, `0.5`, `1.0`) continue to work as expected.

---

## 5. Exact Modified-File Inventory

| File | Changes Made |
|---|---|
| `voice/voice_manager.py` | Removed invalid `is_final=True` parameter from lines 121, 128, and 170. |
| `voice/stt/base.py` | Added `isinstance(self.confidence, bool)` check in `TranscriptionResult.__post_init__`. |
| `voice/stt/vosk_engine.py` | Added `isinstance(raw_conf, bool)` check in `_parse_vosk_dict` before float conversion. |
| `tests/test_stage2a_vosk_confidence.py` | Added 6 new focused regression tests covering Defect A and Defect B. |

---

## 6. New and Updated Regression Tests

6 new tests added to `tests/test_stage2a_vosk_confidence.py` (increasing suite from 21 to 27 tests):

| Test Name | Target Defect | Verification Assertion | Status |
|---|---|---|---|
| `test_11_boolean_confidence_rejected_in_vosk_engine` | Defect B | All-boolean word tokens yield `confidence=None, available=False`, text preserved | **PASSED** |
| `test_12_mixed_boolean_and_valid_word_confidence` | Defect B | Boolean token skipped, valid token `0.8` averaged, `available=True` | **PASSED** |
| `test_transcription_result_rejects_booleans` | Defect B | `True` and `False` yield `None, False`; numeric `0.0` and `1.0` yield valid floats | **PASSED** |
| `test_voice_manager_disabled_branch_no_crash` | Defect A | Disabled branch returns valid `TranscriptionResult(engine="disabled")`, string `""` | **PASSED** |
| `test_voice_manager_busy_branch_no_crash` | Defect A | Busy branch returns valid `TranscriptionResult(engine="busy")`, string `""` | **PASSED** |
| `test_voice_manager_listener_exception_branch_no_crash` | Defect A | Listener exception caught cleanly, returns `engine="error"`, sets `VoiceState.ERROR`, string `""` | **PASSED** |

---

## 7. Test Commands and Actual Outputs

### 1. Stage 2A & 2A.2 Focused Suite
**Command:** `pytest tests/test_stage2a_vosk_confidence.py -v`
```
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_01_valid_word_confidences PASSED [  3%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_02_missing_word_level_confidence PASSED [  7%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_03_empty_text PASSED [ 11%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_04_invalid_confidence_types PASSED [ 14%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_05_negative_confidence_values_ignored PASSED [ 18%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_06_values_greater_than_one_ignored PASSED [ 22%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_07_nan_confidence_ignored PASSED [ 25%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_08_infinite_confidence_ignored PASSED [ 29%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_09_multiple_valid_word_confidences_arithmetic_mean PASSED [ 33%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_10_no_artificial_one_dot_zero PASSED [ 37%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_11_boolean_confidence_rejected_in_vosk_engine PASSED [ 40%]
tests/test_stage2a_vosk_confidence.py::TestVoskConfidenceScenarios::test_12_mixed_boolean_and_valid_word_confidence PASSED [ 44%]
tests/test_stage2a_vosk_confidence.py::TestStructuredResultPreservation::test_01_text_preserved_in_transcription_result PASSED [ 48%]
tests/test_stage2a_vosk_confidence.py::TestStructuredResultPreservation::test_02_confidence_preserved_when_available PASSED [ 51%]
tests/test_stage2a_vosk_confidence.py::TestStructuredResultPreservation::test_03_missing_confidence_marked_unavailable PASSED [ 55%]
tests/test_stage2a_vosk_confidence.py::TestStructuredResultPreservation::test_04_engine_name_preserved PASSED [ 59%]
tests/test_stage2a_vosk_confidence.py::TestStructuredResultPreservation::test_05_recognition_status_and_details_preserved PASSED [ 62%]
tests/test_stage2a_vosk_confidence.py::TestStructuredResultPreservation::test_06_listen_once_backward_compatibility_string PASSED [ 66%]
tests/test_stage2a_vosk_confidence.py::TestStructuredResultPreservation::test_07_malformed_json_handled_safely PASSED [ 70%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_listener_filters_low_confidence_when_available PASSED [ 74%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_listener_does_not_filter_valid_text_when_confidence_unavailable PASSED [ 77%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_voice_manager_listen_once_result_and_backward_compat PASSED [ 81%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_transcription_result_sanitization_post_init PASSED [ 85%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_transcription_result_rejects_booleans PASSED [ 88%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_voice_manager_disabled_branch_no_crash PASSED [ 92%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_voice_manager_busy_branch_no_crash PASSED [ 96%]
tests/test_stage2a_vosk_confidence.py::TestVoicePipelineIntegration::test_voice_manager_listener_exception_branch_no_crash PASSED [100%]
======================== 27 passed, 1 warning in 0.70s ========================
```

### 2. Full Regression Suite Results

| Test Group | Command | Previous Result | New Result | Status |
|---|---|---:|---:|---|
| Stage 2A & 2A.2 Confidence Tests | `pytest tests/test_stage2a_vosk_confidence.py -v` | 21/21 | **27/27** | **PASSED** |
| Stage 1 Browser Routing | `pytest tests/test_stage1_browser_routing.py -v` | 21/21 | **21/21** | **PASSED** |
| Browser Skill Regression | `pytest tests/regression/test_browser_skill.py -v` | 15/15 | **15/15** | **PASSED** |
| Adapter Parity Regression | `pytest tests/regression/test_adapter_parity.py -v` | 6/6 | **6/6** | **PASSED** |
| Execution Pipeline Regression | `pytest tests/regression/test_execution_pipeline.py -v` | 13/13 | **13/13** | **PASSED** |
| Voice Pipeline Regression | `python -m unittest tests/regression/test_voice_pipeline.py` | 14/14 | **14/14** | **PASSED** |
| **TOTAL** | | **90/90** | **96/96** | **100% PASS** |

---

## 8. Before-and-After Behavior

| Scenario | Before Stage 2A.2 Fix | After Stage 2A.2 Fix |
|---|---|---|
| `VoiceManager.listen_once_result()` when `voice_enabled=False` | `TypeError: TranscriptionResult.__init__() got unexpected keyword 'is_final'` | Returns `TranscriptionResult(text="", confidence=0.0, engine="disabled")` |
| `VoiceManager.listen_once()` when `voice_enabled=False` | Crashes with unhandled `TypeError` | Returns empty string `""` cleanly |
| `VoiceManager.listen_once_result()` when busy | Crashes with unhandled `TypeError` | Returns `TranscriptionResult(text="", confidence=0.0, engine="busy")` |
| `VoiceManager.listen_once_result()` on exception | Crashes with unhandled `TypeError` in exception handler | Returns `TranscriptionResult(text="", confidence=0.0, engine="error")`, state `ERROR` |
| `TranscriptionResult(text="t", confidence=True)` | Evaluates to `confidence=1.0, confidence_available=True` | Evaluates to `confidence=None, confidence_available=False` |
| `TranscriptionResult(text="t", confidence=False)` | Evaluates to `confidence=0.0, confidence_available=True` | Evaluates to `confidence=None, confidence_available=False` |
| Vosk word token `{"word": "w", "conf": True}` | Converted to float `1.0`, accepted into arithmetic mean | Logged as warning, skipped; not counted as numeric confidence |
| Numeric confidence `0.0`, `0.5`, `1.0` | Preserved as valid floats | Preserved as valid floats with `confidence_available=True` |

---

## 9. Backward Compatibility Verification

1. `ui/chat.py` line 947: Calls `self.voice_manager.listen_once(status_callback=on_status)`. Now safely receives `""` even if voice is disabled or busy, preventing UI thread exceptions.
2. `voice/voice_manager.py` line 181: Calls `self.listen_once(timeout=timeout, phrase_time_limit=4)`. Preserves string return type.
3. `tests/regression/test_voice_pipeline.py`: Passes all 14 tests without regression.

---

## 10. Database and Configuration Safety Confirmation

- `database/oliver.db`: Untouched and unmodified.
- `database/oliver.db-wal` / `oliver.db-shm`: Untouched.
- `config/voice_settings.json`: Preserved.
- `.env`: Preserved.
- Docker / PostgreSQL / Dependencies: Untouched. Zero packages installed or modified.

---

## 11. Final Git Status

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
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2A2_DEFECT_FIX_REPORT.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2A_VOSK_CONFIDENCE_REPORT.md
?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2_VOICE_SAFETY_AUDIT.md
?? scratch/acc_test_idempotency.py
?? tests/test_api_client.py
?? tests/test_stage1_browser_routing.py
?? tests/test_stage2a_vosk_confidence.py
```
Zero commits staged. No branches switched.

---

## 12. Remaining Limitations

1. **Acoustic Realism:** Unit tests mock audio buffers. Real microphone testing in physical desktop environments remains necessary to evaluate room reverb and microphone gain characteristics.
2. **Denominators on Partial Tokens:** As documented in Stage 2A.1, if a synthetic dictionary contains some valid tokens and some invalid tokens, the arithmetic mean is calculated over valid tokens only. In standard Vosk Kaldi output, Kaldi emits confidences for all words or none.

---

## 13. Final Readiness Recommendation

### **DECISION: PASS — READY FOR STAGE 2B**

Both authorized defects have been corrected, verified, and backed by automated regression tests. The voice pipeline now produces reliable, sanitized transcription metadata in a backward-compatible manner.

**Stage 2B (Cockpit UI Metadata Display) is ready for implementation upon explicit user authorization.**

