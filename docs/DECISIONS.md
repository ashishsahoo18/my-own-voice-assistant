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
