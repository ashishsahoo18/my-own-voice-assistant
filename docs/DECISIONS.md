# Architecture Decision Records (ADRs) — OLIVER 2.0

## ADR 0001: Phase 1 Safety Baseline & Foundation

- **Status**: Accepted
- **Date**: October 8, 2026
- **Context**:
  The existing assistant (formerly AYRA AI / ASHISH AI) required upgrading to OLIVER 2.0. Before making architectural changes to monolithic command dispatching or the UI, a zero-regression safety baseline, verified backup, centralized configuration, structured/redacted logging, and error hierarchy were required.
- **Decision**:
  1. **Git Checkpointing**: Tagged commit `v1-baseline` at the pre-upgrade state on branch `main` and created branch `oliver-2.0` for all changes.
  2. **Verified Backup**: Created a timestamped read-only backup in `backups/v1_baseline_20261008_123925` containing all SQLite databases, `contacts.csv`, `config/voice_settings.json`, and `.env` files. Every file verified with SHA-256 matching.
  3. **Repository Sanitization**: Hardened `.gitignore` to prevent committing logs, SQLite databases, screenshots, and personal address books. Untracked these files from the Git index using `git rm --cached` without deleting local copies on disk.
  4. **Typed Configuration**: Introduced `core/config.py` using Pydantic `BaseModel` for validation, path normalization, environment overrides, and security allowlists. Preserved backward compatibility with `config/settings.py`.
  5. **Structured & Redacted Logging**: Introduced `core/logging.py` with correlation ID tracking via `contextvars`, sensitive secret redaction (masking API keys, passwords, and credit card numbers), rotating file logs, and append-only `audit.jsonl`.
  6. **Typed Error Hierarchy**: Introduced `core/errors.py` with typed exceptions (`OliverError`, `PolicyDenied`, `LLMUnavailable`, etc.) and `format_user_error` mapping to safe user-friendly messages.
  7. **Regression Testing**: Added `tests/__init__.py` and `tests/regression/` test suite ensuring all 19 baseline tests continue to pass alongside new core infrastructure tests.
- **Consequences**:
  - The project is now protected against accidental data loss.
  - Runtime logs and databases will no longer pollute git commits.
  - All existing features and tests remain 100% operational.

## ADR 0002: Phase 2 Skill/Tool Registry & Router Architecture

- **Status**: Accepted
- **Date**: October 8, 2026
- **Context**:
  The previous command architecture used monolithic keyword matching scattered between `AshishAssistant` and `CommandRouter`. We needed a decoupled plugin/skill registry with explicit tool contracts, deterministic-first matching, schema-constrained LLM fallback, and immediate rollback via feature flag.
- **Decision**:
  1. **Contract Definition**: Created `skills.base` declaring `BaseSkill`, `SkillManifest`, `ToolSpec`, `ToolResult`, and `ToolRiskLevel` (Levels 0-3).
  2. **Central Registry**: Created `skills.registry.SkillRegistry` supporting dynamic discovery, manifest validation, health checks, enabling/disabling, and broken-skill isolation.
  3. **Builtin Adapters**: Wrapped all pre-existing command logic into 9 builtin skills (`windows`, `browser`, `youtube`, `files`, `communication`, `contacts`, `info`, `productivity`, `ai`) without modifying underlying command implementations.
  4. **Productivity Hardening**: Replaced dangerous `eval()` arithmetic evaluation in `ProductivitySkill` with an AST-based safe math evaluator.
  5. **LLM Provider**: Formalized `llm.provider.LLMProvider` and `llm.ollama_provider.OllamaProvider` connecting to local `llama3.2:latest`, supporting structured JSON output via Pydantic validation.
  6. **Dual Router Modes**: Added feature flag `router.mode: legacy | oliver`. In `legacy` mode, original command dispatching executes unchanged; in `oliver` mode, deterministic rule routing executes first, falling back to schema-constrained LLM intent classification.
  7. **Drop-in User Skills**: Supported loading external user skills from a `user_skills/` directory.
- **Consequences**:
  - Command handling is decoupled and extensible without editing core code.
  - Immediate rollback capability preserved via `router.mode: legacy`.
  - 100% backward compatibility maintained across all regression tests.

---

### ADR 0003: Central Policy Gate, Action-Bound Confirmation Tokens, and Native Path Sandbox (Phase 3)
- **Status**: Accepted & Implemented
- **Date**: October 8, 2026
- **Context**:
  OLIVER 2.0 has the ability to execute Windows system commands, delete files, and dispatch communications. Without a centralized policy gate, untrusted input or hallucinated model tool calls could trigger destructive operations. Confirmation previously relied on raw string prefixes (`"CONFIRMATION_REQUIRED:..."`) rather than action-bound tokens, and subprocesses used `shell=True` and `eval()`.
- **Decision**:
  1. **Central Policy Gate**: Introduced `security.policy_engine.PolicyEngine`. All tool invocations—whether routed through OLIVER intent matching, legacy command dispatch, direct skill invocation, or external plugins—must evaluate against `PolicyEngine.evaluate()`.
  2. **4-Tier Risk Policy**: Enforced explicit tiers: Risk 0 (SAFE), Risk 1 (LOW), Risk 2 (SENSITIVE), and Risk 3 (DANGEROUS).
  3. **Action-Bound Confirmation Tokens**: Built `security.confirmation.ConfirmationManager` using single-use UUID tokens with exact-effect preview summaries, anti-replay tracking (`_consumed_tokens`), strict yes/no confirmation grammars, and 30-second TTL expiration.
  4. **Path Sandboxing & Safe Deletion**: Implemented `security.sandbox.PathSandbox` enforcing allowlisted directory roots, blocking traversal (`..`) and sensitive Windows system directories (`C:\Windows`, `.ssh`). Replaced permanent deletion with native Windows Recycle Bin transfers via `SHFileOperationW`.
  5. **Emergency Kill Switch & Rate Limiter**: Added `security.kill_switch.KillSwitch` for immediate action halting and token invalidation, plus sliding-window rate limiting for sensitive operations.
  6. **Zero Shell=True & Zero Eval()**: Eradicated all `shell=True` and raw `eval()` calls project-wide, replacing them with AST-based arithmetic parsers and explicit argument lists.
- **Consequences**:
  - The LLM can never make permission decisions or execute destructive commands independently.
  - Replay attacks on confirmation tokens are prevented.
  - Backward compatibility with legacy confirmations (`CONFIRMATION_REQUIRED:...`) is fully maintained.
  - Complete test suite passes (87/87 tests).

---

### ADR 0004: Central Execution Funnel and Post-Execution Verification Pipeline (Phase 4)
- **Status**: Accepted & Implemented
- **Date**: October 8, 2026
- **Context**:
  In earlier phases, tools could report completion without concrete observable verification (e.g. a file operation claiming success even if the file failed to write, or a communication tool asserting delivery without confirmation). To ensure reliability, OLIVER 2.0 requires an authoritative execution funnel where every action follows:
  `TaskRequest -> Validate -> PolicyGate -> Confirm -> Execute -> Verify -> Record -> Report`.
- **Decision**:
  1. **Central Execution Engine**: Implemented `execution.engine.ExecutionEngine`. Every action from OLIVER mode, legacy mode, and direct tool invocations passes through this single funnel.
  2. **Structured TaskRequest**: Created typed `TaskRequest` with correlation IDs, timeout controls, integrity validation, and confirmation state.
  3. **Observable Post-Execution Verifiers**: Created `FileVerifier` (filesystem existence, type, size check, deletion absence), `ProcessVerifier` (active process inspection via `psutil`), `CommunicationVerifier` (honest reporting: `UNVERIFIED` for desktop automation without delivery receipts; never claims false delivery), and `GenericVerifier`.
  4. **Strict Typed States**: Standardized on `VERIFIED`, `UNVERIFIED`, `FAILED`, `DENIED`, `CANCELLED`, and `TIMEOUT`. `UNVERIFIED` is never converted to success, and LLMs are forbidden from inventing verification evidence.
  5. **Graceful Fallback & Bounded Retries**: Implemented deterministic fallback handlers for safe operations (Risk <= 1), bounded to 1 retry.
  6. **Lifecycle Audit Trail**: Recorded execution lifecycle events with correlation IDs: `TASK_REQUESTED`, `TASK_VALIDATED`, `POLICY_CHECKED`, `TASK_EXECUTED`, `VERIFICATION_STARTED`, `VERIFICATION_COMPLETED`, and `TASK_COMPLETED`.
- **Consequences**:
  - Direct execution bypasses are eliminated.
  - Verification is grounded strictly in operating system reality.
  - Complete test suite passes (100/100 tests).

---

### ADR 0005: Unified Database & Hybrid Memory Engine (Phase 5)
- **Status**: Accepted & Implemented
- **Date**: October 12, 2026
- **Context**:
  Legacy OLIVER/AYRA stored data haphazardly across disjoint SQLite databases (`database/ayra_chat.db`, `database/ayra_memory.db`, `database/memory.db`) with varying schemas and lacking foreign keys, WAL concurrency mode, schema version tracking, and deterministic migration deduplication. Furthermore, conversation state, short-term references, and long-term user facts lacked structured separation and strict privacy boundary enforcement.
- **Decision**:
  1. **Unified SQLite Database (`database/oliver.db`)**: Configured with `PRAGMA journal_mode = WAL;`, `foreign_keys = ON;`, `synchronous = NORMAL;`, and `busy_timeout = 5000;`. Schema versioning tracked in `schema_migrations`.
  2. **Additive, Idempotent Legacy Migration**: Implemented `LegacyDataMigrator` which creates timestamped SHA-256 verified backups before migrating. Legacy databases are strictly read-only and never deleted or mutated. Duplicate prevention is enforced deterministically by `UNIQUE(source_db, source_table, source_id)` in `data_migration_log`.
  3. **Three-Tier Hybrid Memory Architecture**:
     - *Working Memory*: Active session buffer, recent candidate entity tracking, and pronoun/ordinal reference resolution ("it", "that one", "the second one", "last one").
     - *Episodic Memory*: Multi-session conversation history with token estimates and structured prompt context formatting.
     - *Semantic Memory*: Long-term facts and user preferences with importance scoring (0.0 to 1.0) and keyword search with access-frequency ranking boost.
  4. **Strict Privacy Policy Gate**: Storage requests deterministically pass through `SensitiveDataFilter`. Passwords, API keys, bearer tokens, OTPs, PINs, and credit card numbers are rejected prior to persistence. The LLM is never permitted to make privacy decisions.
  5. **Explicit User Memory Controls**: First-class commands and skill tools:
     - `what do you remember`
     - `remember that <fact>`
     - `forget <target>` / `forget this memory`
     - `clear session memory`
     - `memory status`
- **Consequences**:
  - Legacy user history (1 session, 8 messages) safely imported and verified.
  - Zero data loss, zero mutation to original legacy files.
  - Full concurrency resilience under WAL mode tested and verified.
  - 121/121 regression tests passing.

---

### ADR 0006: Multi-Step Agentic Task Loop, Bounded Planner, and Task Persistence (Phase 6)
- **Status**: Accepted & Implemented
- **Date**: October 12, 2026
- **Context**:
  Composite user tasks (e.g. creating a folder and saving a file inside it, or calculating figures and recording reminders) require multi-step planning and autonomous orchestration. Without strict boundaries, agents risk runaway execution loops, unverified actions, security policy bypasses, repeated destructive operations, or hallucinated success reports.
- **Decision**:
  1. **Bounded Planning**: Plans strictly bounded to a maximum of 6 steps (`max_plan_steps = 6`). Every plan is validated by `PlanValidator` against schema, sequential numbering, registered tool availability, and security bypass prevention prior to execution.
  2. **Mandatory Central Security Gate**: No agent step executes tools directly. Every step is wrapped in `TaskRequest` and dispatched through `ExecutionEngine.execute()`, enforcing `PolicyEngine`, confirmation checks, sandboxing, and verifiers.
  3. **Step-by-Step Observable Verification**: Each step's outcome is checked against concrete operating system verifiers (`VERIFIED`, `UNVERIFIED`, `FAILED`). A step failure or unverified result immediately halts sequential execution.
  4. **Action-Bound Confirmation**: Actions with Risk >= 2 (Sensitive/Dangerous) require explicit confirmation bound to the exact tool and parameters. Unconfirmed tasks pause cleanly in `WAITING_CONFIRMATION` without executing unapproved steps.
  5. **Bounded Recovery & Replanning**: Recovery is bounded to at most 1 replan attempt (`max_replans = 1`). Infinite replanning loops are impossible. If recovery fails, the task terminates in `REPLAN_EXHAUSTED`.
  6. **Loop & Oscillation Detection**: Implemented `LoopDetector` tracking sliding action history. Immediately halts duplicate identical calls, oscillatory sequences (A-B-A-B), and repeated destructive operations.
  7. **Transactional Task Persistence & Safe Resumption**: Managed via `TaskStore` backed by `agent_tasks` and `agent_task_steps` tables in the unified SQLite database. Interrupted tasks can be inspected and resumed without repeating already-verified completed steps.
  8. **Honest Reporting**: `TaskReport` summaries are constructed strictly from real `ToolResult` statuses and observable verification evidence. LLMs are prohibited from asserting task success without verifier backing.
  9. **Memory Read-Only Context Integration**: Planner reads context from `HybridMemoryEngine` without persisting entire multi-step tasks as permanent facts.
- **Consequences**:
  - Full multi-step autonomy with deterministic safety guards.
  - Resilient cancellation and emergency kill switch support.
  - Complete test suite passes: 134/134 tests passing.




