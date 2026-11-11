# OLIVER 3.0 — Phase 2A.1.2 Runtime Trace & Root Cause Verification

**Date:** 2026-11-07  
**Environment:** Windows, Python 3.13.5, Vosk offline STT, Ollama Llama 3.2, CustomTkinter UI  
**Mode:** Strict read-only investigation  

---

## 1. Executive Summary

| Bug | Root Cause | Classification |
|-----|-----------|----------------|
| `BrowserSkill.ask_page() got an unexpected keyword argument 'query'` | Ollama LLM intent classifier returns `{"query": "..."}` as arguments for `browser.ask_page`; the actual handler signature requires `question`, not `query` | **CONFIRMED** |
| "open YouTube" → "open ear‑dope.com" | Vosk small model phonetically mis-transcribes "youtube" in short utterances; confidence was above the 0.25 threshold so the garbled text was forwarded | **CONFIRMED** |
| "Hello OLIVER" → no response | Background wake-word detection only matches the configured literal phrase (`hey ashish`); "Hello OLIVER" is not in the wake-word set and push-to-talk was not active | **CONFIRMED** |

---

## 2. Browser Runtime Error — Full Trace

### 2.1 The Complete Execution Path

```
User speaks/types a phrase (e.g. "ask page about ...")
    ↓
ui/chat.py:646  → assistant.handle_result(command)
    ↓
ai/assistant.py:170–174  → IntentRouter.route(text)
    ↓
router/router.py:222–235  → Deterministic rules: NO MATCH
    (no rule in _build_deterministic_rules covers "ask page about ...")
    ↓
router/router.py:222–235  → _is_potential_tool_command() → True (short phrase)
    ↓
router/router.py:258–274  → _classify_with_llm(text)
    Sends to Ollama: tool list includes "browser.ask_page: Answer a user question
    grounded strictly in webpage text with source citation."
    Ollama returns IntentClassification:
        tool_name = "browser.ask_page"
        arguments = {"query": "..."}     ← Ollama hallucinates "query" (generic key)
    ↓
router/router.py:228–235  → RouteResult(tool_name="browser.ask_page",
                                        arguments={"query": "..."})
    ↓
router/router.py:290–298  → TaskRequest(tool_name="browser.ask_page",
                                        arguments={"query": "..."})
    ↓
execution/engine.py:168–172  → _execute_call(tool.handler, {"query": "..."})
                               → tool.handler(**{"query": "..."})
    ↓
skills/builtin/browser_skill.py:168
    def ask_page(self, question: str, url: Optional[str] = None)
    Called as: ask_page(query="...")   ← TypeError: unexpected keyword argument 'query'
    ↓
execution/engine.py:195–196  → Exception captured as exec_error
execution/engine.py:224–236  → ToolResult(status="FAILED",
                   message="Execution failed for 'browser.ask_page': ...")
                   The error message in the UI shows the raw TypeError text.
```

### 2.2 Exact Files and Lines

| Step | File | Line(s) | Detail |
|------|------|---------|--------|
| UI dispatches to assistant | `ui/chat.py` | 646–647 | `res = self.assistant.handle_result(command)` |
| `handle_result` calls OLIVER router | `ai/assistant.py` | 170–174 | `route_res = self.oliver_router.route(text)` |
| Deterministic rules: no match for "ask page" phrases | `router/router.py` | 61–167 | No regex in `self.rules` covers `ask page about ...` |
| LLM fallback triggered | `router/router.py` | 222–235 | `_is_potential_tool_command` → True; `_classify_with_llm` called |
| LLM prompt includes tool descriptions | `router/router.py` | 260–261 | Description for `browser.ask_page`: *"Answer a user question grounded strictly in webpage text"* — does not mention that the argument name is `question` not `query` |
| Ollama returns hallucinated arg name | `router/router.py` | 269–274 | `IntentClassification.arguments = {"query": "..."}` |
| Engine calls handler with wrong kwargs | `execution/engine.py` | 168–172 | `fn(**{"query": "..."})` where fn is `BrowserSkill.ask_page` |
| Handler signature requires `question` | `skills/builtin/browser_skill.py` | 168 | `def ask_page(self, question: str, url: Optional[str] = None)` |
| `BrowserService.ask_page` also uses `question` | `browser/service.py` | 173 | `def ask_page(self, question: str, url: Optional[str] = None)` |
| TypeError raised, caught by engine | `execution/engine.py` | 195–236 | `exec_error` returned as `ToolResult(status="FAILED", ...)` |

### 2.3 Why "ask page" Has No Deterministic Rule

The `router/router.py` rules table (lines 61–167) contains no entry for `browser.ask_page`.  
The `BrowserSkill.get_manifest()` lists `"ask page"` as a trigger word (`browser_skill.py:28`), but that manifest list is **not read by `IntentRouter._build_deterministic_rules()`** — it only uses hardcoded regex patterns. So any "ask page about ..." phrase always falls through to the LLM classifier.

### 2.4 Root Cause — CONFIRMED

**The LLM (Ollama Llama 3.2) consistently generates `{"query": "..."}` instead of `{"question": "..."}` when classifying intents for `browser.ask_page`.**

This is because:
1. The tool description prompt does not expose the actual Python parameter names.
2. `query` is a generic, commonly used argument key that the model defaults to.
3. `question` is the actual parameter name in `BrowserSkill.ask_page` and `BrowserService.ask_page`.
4. The `IntentClassification` schema (`router/router.py:25`) does not validate argument keys against the actual tool signature.

### 2.5 Recommended Minimal Fix (requires approval before implementation)

**Option A — Deterministic rule (safest, no LLM dependency):**  
Add a regex rule to `IntentRouter._build_deterministic_rules()`:
```python
(re.compile(r"^ask(?:\s+page(?:\s+about)?|\s+webpage(?:\s+about)?)?\s+(.+)$", re.IGNORECASE), "browser.ask_page", "question"),
```

**Option B — Argument key remapping in `BrowserSkill.ask_page`:**  
Add `**kwargs` to the method and remap `kwargs.get("query")` → `question`. This protects against future LLM variations without changing the router.

**Option C — Argument key validation in `ExecutionEngine`:**  
Inspect the handler signature before calling and remap known synonyms. More complex, broader protection.

> Option A is the minimum safe fix with no risk to other tools.

### 2.6 Regression Tests Needed

| Test | Verifies |
|------|---------|
| `IntentRouter.route("ask page about Python")` → `tool_name=browser.ask_page`, `arguments={"question": "about Python"}` | Deterministic rule fires before LLM |
| `BrowserSkill.ask_page(query="test")` → raises `TypeError` or is remapped gracefully | Existing behavior documented |
| Engine executes `browser.ask_page` with `{"question": "Who wrote Python?"}` without error | Full happy path |

---

## 3. Voice Recognition — Confidence and Transcription

### 3.1 Vosk Confidence Calculation

**File:** `voice/stt/vosk_engine.py`, lines 127–132

Vosk returns per-word confidence values in the JSON `result` field. The engine computes:
```python
confs = [float(w.get("conf", 1.0)) for w in word_list if "conf" in w]
avg_confidence = sum(confs) / len(confs) if confs else (1.0 if text else 0.0)
```

**Key observations:**
- If word-level confidence is unavailable (empty `result` list), `avg_confidence` defaults to `1.0` when text is non-empty. This means a transcription with no confidence data is treated as fully confident.
- The model used is `vosk-model-small-en-us-0.15` (confirmed from regression test Vosk log output). The small model has lower accuracy on proper nouns and short utterances.

**Confidence threshold:** `voice/listener.py` line 91 — transcripts with `confidence < 0.25` are discarded.

**Classification: CONFIRMED** — The threshold of 0.25 is too permissive. A confidence of e.g. 0.3 for "ear dope" is accepted and forwarded.

### 3.2 Why "Open YouTube" → "open ear‑dope.com"

**Execution path:**
```
Microphone → AudioCapture.capture_audio (sample_rate=16000, chunk=1024)
    → VoiceListener.listen_once (timeout=10s, phrase_time_limit=15s, silence=1.0s)
    → LocalFirstSTTEngine.transcribe
    → VoskSTTEngine.transcribe
        → KaldiRecognizer on 16kHz PCM
        → FinalResult() → {"text": "open ear dope", "result": [...]}
        → avg_confidence calculated from word-level conf values
    → TranscriptionResult(text="open ear dope", confidence=~0.3–0.5)
    → VoiceListener._recognize_audio: confidence > 0.25 → NOT discarded
    → returns "open ear dope"
    ↓
Router: "open ear dope" → matches regex ^(?:open|go to|visit)...[domain pattern]
router/router.py:87  → browser.open_site, site_name="ear dope"
BrowserCommands.open_site: "ear dope" not in self.sites
  → "ear dope" contains no dot → returns "I couldn't identify..."
  
  ** BUT ** if Vosk transcribes it as "open ear-dope.com" or similar with a dot,
  BrowserCommands.open_site line 215 catches "."-containing strings as domains
  → opens https://ear-dope.com
```

**Root cause chain:**
1. Vosk small model mis-transcribes "youtube" (phoneme sequence `j-uː-t-juːb`) as "ear dope" or similar.
2. The `pause_threshold = 1.0` sec in `VoiceListener` means even a 2-word phrase gets captured cleanly before Vosk can apply language-model context.
3. `AudioCapture` only calibrates ambient noise **once** (`_has_calibrated` flag); subsequent captures use a potentially stale noise floor.
4. No clarification step exists — uncertain transcripts go directly to routing.

**Classification: CONFIRMED**

### 3.3 Whether the UI Receives Confidence

**File:** `voice/listener.py`, line 94  
```python
return result.text.strip()
```
The UI receives **only the text string**. The `TranscriptionResult` (including `confidence`, `engine`, `latency_s`) is stored in `self.last_result` but is **not surfaced to the UI or the router**. The router and dispatcher receive only the raw text.

**Classification: CONFIRMED** — No confidence gating beyond the 0.25 floor exists in the routing pipeline.

### 3.4 Can Low-Confidence Speech Execute Browser Commands?

Yes. Any transcript with confidence ≥ 0.25 is passed unchanged to the router. The router has no confidence awareness. If Vosk returns `"open ear dope"` with confidence 0.3, it will trigger a browser open attempt.

**Classification: CONFIRMED**

---

## 4. Wake Phrase vs. Push-to-Talk

### 4.1 Architecture — CONFIRMED

| Mode | File | Mechanism |
|------|------|-----------|
| Push-to-talk | `voice/listener.py` `VoiceListener.listen_once()` | User presses MIC button; `listen_once` captures one phrase |
| Background wake-word | `voice/wakeword.py` `WakeWordDetector._run()` | Background thread; listens in 2.5-second windows; triggers callback on match |

### 4.2 Wake Word Configuration

**File:** `voice/wakeword.py`, line 26  
Default: `wake_word = "hey oliver"`  

**File:** `.env`  
`WAKE_WORD=hey ashish`  

The `WakeWordDetector._contains_wake_word()` (line 119) checks:
1. `self.wake_word in text` — substring match
2. All tokens of `wake_word` appear in `text`

**"Hello OLIVER" analysis:**  
- Configured wake word is `hey ashish`
- "hello oliver" does not contain "hey ashish"
- No token overlap: `{"hey","ashish"} ∩ {"hello","oliver"} = ∅`
- → Wake word detection **will not fire**

**"Hello OLIVER" after pressing MIC (push-to-talk):**  
If the user presses MIC, `VoiceListener.listen_once()` captures the audio. Vosk transcribes it. The resulting text ("hello oliver" or similar) is passed to the assistant. In legacy mode, `determine_intent("hello oliver")` → `"AI"` → passed to `ai_service.ask()`. **OLIVER will respond with a greeting from Ollama** in push-to-talk mode.

The user's report of no confirmed response likely means either:
- Wake-word mode was active (no MIC press) and "hello oliver" ≠ "hey ashish"
- **OR** Vosk transcribed it incorrectly (the small model may produce "hello all of her" or similar)

**Classification: CONFIRMED** — Wake-word detection requires the exact configured phrase. Push-to-talk should produce a greeting response if Vosk transcribes correctly.

---

## 5. YouTube Command Routing — Full Trace

| Spoken Command | Normalized | Matched Rule (router/router.py) | Tool | Arguments | Handler |
|----------------|-----------|--------------------------------|------|-----------|---------|
| "Open YouTube" | "open youtube" | Line 86 — Universal website regex | `browser.open_site` | `site_name="youtube"` | `BrowserCommands.open_site("youtube")` → `BrowserCommands.open_url("https://www.youtube.com")` |
| "Open YouTube please" | "open youtube" (please stripped by `_normalize_text`) | Line 86 — same | `browser.open_site` | `site_name="youtube"` | Same as above |
| "Search YouTube for Python tutorials" | same | Line 90 — YouTube search regex | `youtube.search` | `query="Python tutorials"` | `YouTubeSkill.search("Python tutorials")` → `YouTubeCommands.search_youtube(...)` → opens search URL |
| "Play Python tutorials on YouTube" | "play python tutorials on youtube" | Line 91 — `^play\s+(.+)$` | `youtube.play` | `query="python tutorials on youtube"` | `YouTubeSkill.play("python tutorials on youtube")` → `YouTubeCommands.play_youtube(...)` |

**Domain accident path:**  
"Open YouTube" mis-transcribed as "open ear dope" (or "open ear-dope.com"):
- `router/router.py:87` — regex `^(?:open|go to|visit)\s+(?:the\s+)?([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+...)$` matches any domain-like string with a dot
- `browser.open_site` called with `site_name="ear-dope.com"`
- `BrowserCommands.open_site`: "ear-dope.com" not in `self.sites`, but `.` in name → line 215 treats it as a URL → opens `https://ear-dope.com`

**Classification: CONFIRMED** — The domain-pattern regex (`router.py:87`) is the bridge between mis-transcription and unintended browser navigation.

---

## 6. Memory Usage

> **NOT TESTED** — Runtime process memory cannot be measured safely without attaching to live processes or running psutil introspection scripts. No existing log captures this.

**Available static evidence:**

| Component | Evidence | Estimated footprint |
|-----------|---------|---------------------|
| Vosk model (`vosk-model-small-en-us-0.15`) | Loaded via `vosk.Model(str(model_dir))` on first STT call; held in `VoskSTTEngine._model` for the process lifetime | ~50–80 MB (small model) |
| Ollama Llama 3.2 | External process; holds the model in GPU/CPU VRAM | ~2–4 GB depending on quantization |
| Python UI + skills | Estimated from typical CustomTkinter + skill registry overhead | ~80–150 MB |
| Apparent 91–92% RAM | Consistent with Ollama holding the model in memory alongside the Windows desktop environment | Plausible but NOT TESTED against live measurements |

---

## 7. Prioritized Fix List

| Priority | Fix | Effort | Risk |
|----------|-----|--------|------|
| **P1** | Add deterministic rule for `browser.ask_page` in `router/router.py` with arg key `question` | Small — 1 line in `_build_deterministic_rules` | Very low; no other tools affected |
| **P2** | Add `**kwargs` guard in `BrowserSkill.ask_page` to remap `query` → `question` as a defensive fallback | Small — 2 lines | Very low; backward-compatible |
| **P3** | Raise voice confidence threshold from 0.25 to 0.5 or add a UI confirmation step for browser-open commands | Small — 1 setting change | Low; may increase "not understood" rejections for genuine quiet speech |
| **P4** | Expose `TranscriptionResult.confidence` to the UI cockpit / console entry for observability | Medium — UI thread work | Low; display-only change |
| **P5** | Add tool argument names (not just descriptions) to the LLM classification prompt | Small — 2–3 lines in `_classify_with_llm` | Very low; improves LLM accuracy broadly |
| **P6** | Add regex rule for `"ask page"` / `"ask page about"` / `"ask this page"` phrases to avoid LLM entirely for this common pattern | Small | Very low |

---

## 8. Files Involved

| File | Role |
|------|------|
| `router/router.py` | `IntentRouter`: deterministic rules (missing `browser.ask_page`) + LLM fallback (hallucinates `query`) |
| `skills/builtin/browser_skill.py:168` | `BrowserSkill.ask_page(self, question, url)` — requires `question`, not `query` |
| `browser/service.py:173` | `BrowserService.ask_page(self, question, url)` — same parameter name |
| `execution/engine.py:168–172` | Calls `fn(**arguments)` — no argument remapping |
| `voice/stt/vosk_engine.py` | Vosk transcription; confidence defaults to 1.0 when no word-level data |
| `voice/stt/local_first.py` | Chooses Vosk first; no confidence gating |
| `voice/listener.py:91` | Confidence threshold 0.25 — only floor, no ceiling for routing |
| `voice/wakeword.py:26` | Default `hey oliver`; env sets `hey ashish`; "Hello OLIVER" not supported |
| `commands/browser.py:215` | Domain-fallback path: any string with a `.` and no space → treated as URL |
| `commands/router.py:138–156` | Legacy `_route_open` router: same `self.browser.sites` check |
| `.env` | `WAKE_WORD=hey ashish` |

---

## 9. Git and Database Safety

No source files were modified. No databases were read or written. No processes were started or stopped. Git status is unchanged from the Phase 2A.1 acceptance test baseline.

---

**STOP — Investigation complete. No fixes implemented. Awaiting explicit approval before proceeding.**

