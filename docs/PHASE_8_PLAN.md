# OLIVER 2.0 — Phase 8 Capability Expansion Plan

**Date:** October 13, 2026  
**Status:** Capabilities 1, 2, 3, 4, and 5 COMPLETED & VERIFIED; Capabilities 6–7 Pending Approval  
**Target Branch:** `oliver-2.0`  

---

## 1. Executive Summary & Audit of Existing Capabilities

During Phase 0 through Phase 7, OLIVER 2.0 established:
- Typed configuration, structured logging, and migration framework (Phase 1).
- Local-first Ollama LLM provider with model-probing and graceful offline fallbacks (Phase 2).
- Formal Skill Registry with manifest validation and permission gates (Phase 3).
- Central ExecutionEngine, Verifier pipeline, and PolicyEngine security gates (Phase 4).
- Safe multi-step Agent task planner with loop prevention and replanning caps (Phase 5).
- Dual-tier Hybrid Memory engine with privacy filtering and semantic recall (Phase 6).
- Modular real-time audio pipeline with offline Vosk STT, interruptible TTS, safe barge-in, and action-bound confirmations (Phase 7).

Phase 8 expands high-value domain capabilities while strictly maintaining zero paid APIs, security boundaries, and full test suite regression compliance. Capabilities 1 (Research Assistant), 2 (Coding Assistant), 3 (Documents & Knowledge), 4 (Browser Automation), and 5 (Productivity Assistant) are fully implemented and verified.

---

## 2. Audit: Existing vs. Missing Capabilities

| Capability Domain | Existing Baseline Functionality | Missing High-Value Functionality | Status / Priority Tier |
| :--- | :--- | :--- | :--- |
| **1. Research Assistant** | `commands/browser.py` opens URLs in the user's browser via `webbrowser.open()`. | Structured web queries (Wikipedia API, DuckDuckGo API/HTML), clean text extraction, fact extraction, source URL attribution, uncertainty distinction, prompt injection defense, SSRF blocking, and offline fallback. | **COMPLETED & VERIFIED (Phase 8.1)** |
| **2. Coding Assistant** | Generic Ollama `ai.ask` conversational responses. No structured coding skill, error inspection, or safe code generation pipeline. | Code explanation, syntax/runtime error debugging, patch generation, language detection, and strict non-execution policy gates. | **COMPLETED & VERIFIED (Phase 8.2)** |
| **3. Documents & Knowledge** | `commands/files.py` basic file CRUD (create/read/delete). `memory/semantic_memory.py` vector-like memory items. | Multi-format reader (TXT, MD, PDF, JSON), document chunking, summary generation, local knowledge index, and granular deletion controls. | **COMPLETED & VERIFIED (Phase 8.3)** |
| **4. Browser Automation** | `commands/whatsapp.py` blind `pyautogui.press("enter")` delay. `selenium` installed but unmanaged and unconstrained. | Managed headless/visible browser profile, strict domain allowlist, policy-gated navigation, explicit user consent, and zero bypass of auth/CAPTCHAs. | **COMPLETED & VERIFIED (Phase 8.4)** |
| **5. Productivity** | `commands/reminders.py` basic reminder SQLite store; `commands/productivity.py` simple stopwatch. | Verified task state transitions, recurrence rules, daily briefing aggregator (weather + schedule + system health), and reliable verification. | **COMPLETED & VERIFIED (Phase 8.5)** |
| **6. Vision & OCR** | `commands/screenshot.py` screen capture via PyAutoGUI. `opencv-python` and `Pillow` installed. | Local image analysis (Ollama `llava`), optional OCR text extraction, explicit permission prompts, zero automatic cloud uploads. | **P6** |
| **7. Communication** | `commands/whatsapp.py` and `commands/email_service.py` with basic confirmation prompts. | Recipient preview cards, verified delivery checks, status reporting (`SENT`, `FAILED`, `UNVERIFIED`), and credential security. | **P7** |

---

## 3. Recommended First Capability: Research Assistant

### Why Research Assistant is Selected First
1. **Highest user impact:** Fixes the most visible user frustration where asking for factual information either opens unwanted browser windows or causes ungrounded LLM hallucinations.
2. **Zero new dependencies:** The required libraries are already installed and tested in this Python 3.13 environment: `requests` (2.32.5), `beautifulsoup4` (4.14.2), and `wikipedia` (1.4.0).
3. **Establishes core safety patterns:** Implements the untrusted-data boundary (web content cannot instruct the LLM or bypass security), citation format standards, and graceful offline degradation.
4. **Natural bridge to Agent & Memory:** Allows the Phase 5 Agent loop and Phase 6 Semantic Memory to store and verify real-world facts with source provenance.

---

## 4. Capability 1: Research Assistant Detailed Specification

### 4.1 Functional Scope
- **Online Search & Retrieval:** Query approved information sources:
  1. *Wikipedia API* for encyclopedic topics, historical events, definitions, and technical overviews.
  2. *DuckDuckGo Instant Answer / Web Search* for current facts, zero-click summaries, and public websites without API keys or paid accounts.
- **Content Extraction & Sanitization:**
  - Strip HTML tags, scripts, tracking pixels, ads, and navigation menus using `BeautifulSoup`.
  - Enforce max-content size limit (e.g., 20 KB per page) to prevent context overflow or denial-of-service.
- **Fact-Grounded Summarization:**
  - Synthesize extracted information into a structured response containing:
    - **Key Findings:** 2–4 concise bullet points.
    - **Verified Sources:** Clickable source URLs (`[Source Name](url)`).
    - **Confidence & Uncertainty:** Explicit disclosure if sources conflict or details are unverifiable.
- **Offline Mode & Graceful Degradation:**
  - Detect offline state before attempting network requests.
  - Query local Semantic Memory or Ollama offline knowledge base.
  - Clearly disclose: `"Offline Mode: Response generated from local knowledge; live web verification unavailable."`
- **Prompt Injection Defense:**
  - Wrap fetched web text in isolated XML data blocks (e.g., `<web_context source="...">...</web_context>`).
  - Instruct the model that web context is **untrusted external data** and must never be interpreted as system commands, role changes, or instructions.

### 4.2 Architecture & Module Plan

```
[User Query / TaskRequest]
        │
        ▼
[ResearchSkill] (skills/builtin/research_skill.py)
   ├── [ResearchClient] (research/client.py)
   │      ├── Wikipedia provider
   │      ├── DuckDuckGo provider
   │      └── ContentExtractor (HTML -> Clean text)
   │
   ├── [PromptIsolation] (research/sanitizer.py)
   │      └── Strips dangerous tokens, wraps untrusted content
   │
   └── [FactSummarizer] (research/summarizer.py)
          ├── Ollama local synthesis
          └── Offline fallback handler
        │
        ▼
[ToolResult] (status, message, data={sources, facts, verified, is_offline})
```

### 4.3 Files to Create / Modify

1. **New Modules:**
   - `research/__init__.py`: Package entry point.
   - `research/models.py`: Dataclasses for `ResearchQuery`, `ResearchSource`, `ResearchResult`.
   - `research/providers.py`: Abstract `SearchProvider` with `WikipediaProvider` and `DuckDuckGoProvider`.
   - `research/extractor.py`: HTML sanitizer and text chunker with length bounds.
   - `research/summarizer.py`: Fact extraction, citation generator, and offline fallback synthesizer.
   - `skills/builtin/research_skill.py`: Tool definitions registered in `SkillRegistry`:
     - `research.search(query: str, max_results: int = 3)`
     - `research.summarize_topic(topic: str)`
     - `research.fetch_page(url: str)`

2. **Integration Touchpoints:**
   - `skills/builtin/__init__.py`: Register `ResearchSkill` in `register_all_builtin_skills()`.
   - `ai/assistant.py`: Add research query routing in both legacy and OLIVER modes.
   - `execution/verifiers.py`: Add verification that returned sources are valid URLs.

3. **New Test Suite:**
   - `tests/regression/test_research_skill.py`: Unit and regression tests covering providers, sanitization, injection defense, citations, timeouts, and offline fallback.

---

## 5. Security, Safety, and Privacy Rules

1. **Untrusted Data Isolation:**
   - External web content is strictly treated as passive reference data, never executable instructions.
   - Strip prompt injection patterns (e.g., `"Ignore previous instructions"`, `"System: you are now..."`).
2. **Network Safety & Path Restrictions:**
   - Outbound HTTP requests only to HTTP/HTTPS public protocols.
   - Deny `file://`, `gopher://`, or local network / private IP ranges (`127.0.0.1`, `192.168.*`, `10.*`) to prevent SSRF (Server-Side Request Forgery).
   - Strict request timeouts (default 5.0 seconds).
3. **Privacy & Data Minimization:**
   - Do not send user credentials, personal identity, or sensitive memories in outbound search queries.
   - Log URLs and query terms to the audit logger (`AUDIT.md` standards) without leaking personal tokens.
4. **No Paid APIs:**
   - All research capabilities use public, free endpoints (Wikipedia REST API, DuckDuckGo Instant Answer) or local Ollama summarization.

---

## 6. Implementation Steps for Capability 1

1. **Step 1: Research Core Data Models & Providers (`research/`)**
   - Implement `ResearchSource`, `ResearchResult`, `WikipediaProvider`, `DuckDuckGoProvider`.
   - Add network availability detection and offline simulation hooks.
2. **Step 2: Content Sanitization & Injection Defense (`research/extractor.py`)**
   - Implement HTML cleanup, maximum length clipping, and prompt isolation wrappers.
3. **Step 3: Fact-Grounded Summarizer (`research/summarizer.py`)**
   - Implement synthesis pipeline with source URL attribution and offline handling.
4. **Step 4: ResearchSkill Integration (`skills/builtin/research_skill.py`)**
   - Implement `ToolSpec` definitions (`research.search`, `research.summarize_topic`).
   - Register in `SkillRegistry` and wire into `ExecutionEngine`.
5. **Step 5: Router & Assistant Integration**
   - Enable `search for ...`, `research ...`, and `find information about ...` intent matching.
6. **Step 6: Comprehensive Test Suite & Smoke Testing**
   - Unit tests with mocked HTTP responses.
   - Offline fallback tests.
   - SSRF protection tests.
   - Prompt injection resilience tests.
   - Full regression suite execution (`scripts/test.ps1`).

---

## 7. Acceptance Criteria for Capability 1

- [x] `research.search` returns verified findings with clickable source URLs for public knowledge topics.
- [x] Offline mode correctly returns local facts and discloses that live web verification was unavailable.
- [x] Attempted SSRF to local IP addresses (`127.0.0.1`, `localhost`) is blocked (with DNS rebinding defense and RFC 6052 NAT64 mapping support).
- [x] Prompt injection payloads embedded in web content do not hijack the assistant's instructions (isolated in untrusted data delimiters and defused).
- [x] Zero paid API keys required (free Wikipedia API, DuckDuckGo HTML/Instant Answer, local Ollama).
- [x] All existing 148 regression tests continue to pass without failure.
- [x] New tests for research capability pass cleanly (14/14 tests in `test_research_skill.py`, 162/162 overall suite tests passing).

---

## 8. Capability 1 Verification Summary

- **Implementation Date:** October 13, 2026
- **Test Suite:** `tests/regression/test_research_skill.py` (14 unit/regression tests)
- **Full Suite Status:** 162 passed in 63.2s via `scripts/test.ps1`.
- **Zero Regressions:** V1 commands, Ollama offline fallbacks, SkillRegistry, ExecutionEngine, PolicyEngine, Agent task loops, Hybrid Memory, and Vosk Voice Pipeline intact.

