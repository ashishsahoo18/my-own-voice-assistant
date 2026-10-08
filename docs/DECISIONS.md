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
