# OLIVER 3.0 — Phase 2.1A Remaining Roadmap & Stage 2.1A.1 PostgreSQL Configuration Readiness Report

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A1_POSTGRESQL_CONFIGURATION_READINESS_REPORT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Migration  
**Stage:** 2.1A.1 Planning & Readiness Audit  
**Report Date:** 2026-11-20  
**Audit Mode:** STRICTLY READ-ONLY — Planning and analysis only. Zero implementation. Zero source modifications.  
**Preceding Audit:** `docs/OLIVER_3_PHASE_2_1A0_FINAL_IMPLEMENTATION_VERIFICATION_AUDIT.md`

---

## 1. Executive Summary

This report provides a comprehensive readiness assessment for the remaining OLIVER 3.0 Phase 2.1A PostgreSQL migration roadmap, with deep analysis of Stage 2.1A.1 (PostgreSQL Environment & Configuration).

**Key findings from repository inspection:**

1. **Stage 2.1A.0 is preserved and intact.** Both modified source files are confirmed unchanged since the implementation commit.
2. **Docker is not installed** on the host system. `docker` is not recognized as a command. This is a **hard prerequisite blocker** for Stages 2.1A.1 through 2.1A.8.
3. **psycopg is not installed.** Neither `psycopg`, `psycopg2`, nor `psycopg2-binary` are present in the Python environment.
4. **A backend `.env` does not exist.** Only `backend/.env.example` exists. The root `.env` (254 bytes, dated 18-09-2026) contains only desktop UI configuration (no database URL for the backend).
5. **`alembic.ini` has a hardcoded SQLite URL** (`sqlalchemy.url = sqlite:///./backend/oliver_dev.db`). This static value will conflict with PostgreSQL migration unless overridden. The `env.py` correctly reads from `settings.DATABASE_URL` at runtime, overriding `alembic.ini`. But the static fallback is a documentation hazard.
6. **All 5 ORM models** (`User`, `Conversation`, `Message`, `RefreshToken`, `Device`) use `String(36)` for UUIDs (not native PostgreSQL `UUID` type). All PKs use Python-side `uuid.uuid4()` generation. This is functionally correct on PostgreSQL but not idiomatic — this is a design decision to document, not block on.
7. **Database files are intact.** `database/oliver.db` (192,512 bytes) and `backend/oliver_dev.db` (94,208 bytes) remain unchanged.

**Final readiness verdict: READY WITH CONDITIONS**

Stage 2.1A.1 planning can proceed. However, **Docker Desktop must be installed before Stage 2.1A.4**, and **psycopg must be installed before Stage 2.1A.5**. Stage 2.1A.1 itself (configuration design only) has zero infrastructure prerequisites and can begin immediately upon authorization.

---

## 2. Actual Repository Baseline

### 2.1 Git State

| Property | Value |
|---|---|
| Active Branch | `main` |
| HEAD Commit | `360a154f5d84ac7b47128d855f6d808a2ba7319e` |
| HEAD Message | `Create OLIVER_3_PHASE_2_1A0_FINAL_IMPLEMENTATION_VERIFICATION_AUDIT.md` |
| Previous Commit | `b48411344` ("New database added.") — Stage 2.1A.0 implementation |
| Tracked Modifications | 0 files modified |
| Untracked Files | 0 |

### 2.2 Database Integrity

| File | Size (Bytes) | Last Modified | Status |
|---|---|---|---|
| `database/oliver.db` | 192,512 | 07-11-2026 19:38:26 | **INTACT — Unmodified** |
| `backend/oliver_dev.db` | 94,208 | 07-11-2026 18:12:44 | **INTACT — Unmodified** |

### 2.3 Key Configuration Files Found

| File | Status | Key Finding |
|---|---|---|
| `backend/.env.example` | Present (841 bytes) | Contains DATABASE_URL placeholder; not `.gitignored` per rules |
| `backend/.env` | **ABSENT** | No backend-specific `.env` exists |
| `.env` (root) | Present (254 bytes) | Desktop UI config only; no DATABASE_URL |
| `backend/alembic.ini` | Present (680 bytes) | Line 8: hardcoded `sqlalchemy.url = sqlite:///./backend/oliver_dev.db` |
| `backend/alembic/env.py` | Present (57 lines) | Correctly reads `settings.DATABASE_URL` at runtime (overrides ini) |
| `docker-compose.yml` | **ABSENT** | Not yet created |
| `Dockerfile` | **ABSENT** | Not yet created |

### 2.4 Infrastructure Status

| Component | Status | Evidence |
|---|---|---|
| Docker Desktop | **NOT INSTALLED** | `docker` command not found in PATH |
| psycopg (v3) | **NOT INSTALLED** | `pip show psycopg` returns nothing |
| psycopg2 | **NOT INSTALLED** | `pip show psycopg2` returns nothing |
| Python | **3.13.5** | Confirmed |
| SQLAlchemy | In `requirements.txt`: `>=2.0.30` | Installed |
| Alembic | In `requirements.txt`: `>=1.13.0` | Installed |

---

## 3. Stage 2.1A.0 Preservation Verification

Both Stage 2.1A.0 source files verified intact by `git status --short` returning clean working tree and by reviewing `git log`:

- `backend/app/main.py`: Last modified in commit `b484113`. No subsequent changes.
- `backend/tests/conftest.py`: Last modified in commit `b484113`. No subsequent changes.

Both database files remain at pre-implementation byte sizes and timestamps. Stage 2.1A.0 is preserved.

---

## 4. ORM Model Schema Survey (For Stage 2.1A.3 Planning)

Inspection of all 5 models reveals the following schema:

### 4.1 `users` Table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `String(36)` | PK, index | UUID stored as VARCHAR(36), Python-side generation |
| `email` | `String(255)` | Unique, index, NOT NULL | |
| `hashed_password` | `String(255)` | NOT NULL | |
| `full_name` | `String(255)` | default="OLIVER User", NOT NULL | |
| `preferences` | `Text` | default=JSON string, NOT NULL | JSON stored as TEXT |
| `is_active` | `Boolean` | default=True, NOT NULL | |
| `created_at` | `DateTime(timezone=True)` | NOT NULL | UTC aware |
| `updated_at` | `DateTime(timezone=True)` | NOT NULL, onupdate | UTC aware |

**Relationships:** One-to-many to `refresh_tokens`, `conversations`, `devices` (all cascade delete-orphan)

### 4.2 `conversations` Table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `String(36)` | PK, index | |
| `user_id` | `String(36)` | FK→`users.id` CASCADE, index, NOT NULL | |
| `title` | `String(255)` | default="New Chat", NOT NULL | |
| `created_at` | `DateTime(timezone=True)` | NOT NULL | |
| `updated_at` | `DateTime(timezone=True)` | NOT NULL, onupdate | |

### 4.3 `messages` Table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `String(36)` | PK, index | |
| `conversation_id` | `String(36)` | FK→`conversations.id` CASCADE, index, NOT NULL | |
| `user_id` | `String(36)` | FK→`users.id` CASCADE, index, NOT NULL | |
| `role` | `String(50)` | NOT NULL | "user", "assistant", "system" |
| `content` | `Text` | NOT NULL | |
| `latency_ms` | `Float` | NULLABLE | |
| `created_at` | `DateTime(timezone=True)` | NOT NULL | |

**Note:** `messages` has two FKs: one to `conversations.id` and one to `users.id`. Alembic must generate both.

### 4.4 `refresh_tokens` Table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `String(36)` | PK, index | |
| `user_id` | `String(36)` | FK→`users.id` CASCADE, index, NOT NULL | |
| `token_hash` | `String(64)` | Unique, index, NOT NULL | SHA-256 hex |
| `expires_at` | `DateTime(timezone=True)` | NOT NULL | |
| `revoked` | `Boolean` | default=False, NOT NULL | |
| `created_at` | `DateTime(timezone=True)` | NOT NULL | |

### 4.5 `devices` Table

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `String(36)` | PK, index | |
| `user_id` | `String(36)` | FK→`users.id` CASCADE, index, NOT NULL | |
| `device_name` | `String(255)` | NOT NULL | |
| `device_type` | `String(50)` | default="desktop", NOT NULL | |
| `platform` | `String(50)` | default="windows", NOT NULL | |
| `client_version` | `String(50)` | default="3.0.0", NOT NULL | |
| `registered_at` | `DateTime(timezone=True)` | NOT NULL | |
| `last_active_at` | `DateTime(timezone=True)` | NOT NULL, onupdate | |

### 4.6 Foreign Key Relationship Graph

```
users (1) ──── (N) refresh_tokens
users (1) ──── (N) conversations ──── (N) messages
users (1) ──── (N) messages  [direct FK on messages.user_id]
users (1) ──── (N) devices
```

**Migration ordering requirement:** `users` must be created first. `conversations` before `messages`. All FKs reference `users.id`.

### 4.7 SQLite-Specific Considerations for PostgreSQL Migration

| Consideration | Description | Impact on Migration |
|---|---|---|
| UUID as `String(36)` | Stored as VARCHAR(36), not PostgreSQL native `UUID` type | Functionally correct; not idiomatic. Migration uses VARCHAR(36). Native UUID type migration is a separate future decision. |
| `PRAGMA foreign_keys=ON` | Enforced in SQLite via event listener in `database.py` | PostgreSQL enforces FKs natively; the event listener is SQLite-only and correct. |
| `DateTime(timezone=True)` | SQLite stores as text; PostgreSQL uses `TIMESTAMPTZ` | Alembic generates `TIMESTAMP WITH TIME ZONE` for PostgreSQL. Correct. |
| `Text` for preferences JSON | SQLite stores JSON as text | PostgreSQL could use `JSONB` for indexable JSON, but `Text` is compatible. Future optimization. |
| `String(36)` length | VARCHAR(36) | Compatible with PostgreSQL. |
| Python-side UUID generation | `default=lambda: str(uuid.uuid4())` | Works correctly on both backends; no server-side `gen_random_uuid()` needed. |

---

## 5. Complete Remaining Roadmap

The proposed stage order is correct with one clarification: Stage 2.1A.4 (Docker Infrastructure) **must precede** Stage 2.1A.5 (Integration & Test Validation) because a live PostgreSQL container is required for integration testing. The roadmap order is correct as presented. One split is recommended:

**Stage 2.1A.3 should be split into:**
- Stage 2.1A.3a: Generate and review the initial Alembic migration (offline, no container)
- Stage 2.1A.3b: Apply the migration against the live container (requires 2.1A.4)

This split is documented below. The stage numbers are preserved for consistency.

### Stage 2.1A.1 — PostgreSQL Environment & Configuration
**Deliverable:** Configuration design, `backend/.env.example` update, connection pooling recommendations, failure behavior specification.  
**Prerequisites:** Stage 2.1A.0 complete ✅  
**Docker required:** No — this is configuration design only.

### Stage 2.1A.2 — PostgreSQL Roles & Permissions
**Deliverable:** Complete role model design, SQL provisioning scripts.  
**Prerequisites:** Stage 2.1A.1 — URL and environment design must be finalized before writing role provisioning scripts.  
**Docker required:** No — this is design only.

### Stage 2.1A.3 — Initial Alembic Migration
**Deliverable:** Generated Alembic migration revision file, reviewed and approved.  
**Prerequisites:** Stage 2.1A.2 — Alembic must run as the correct migration role.  
**Docker required:** No for generation (offline mode); Yes for application.

### Stage 2.1A.4 — Docker PostgreSQL Infrastructure
**Deliverable:** `docker-compose.yml`, `docker-entrypoint-initdb.d/` SQL scripts, volume definition, health checks.  
**Prerequisites:** Stage 2.1A.1 (config), Stage 2.1A.2 (roles). Docker Desktop must be installed first.  
**Docker required:** Yes — explicit prerequisite.

### Stage 2.1A.5 — Database Integration & Test Validation
**Deliverable:** Live connection verification, migration application, all 14 Category A tests passing, Category B framework ready.  
**Prerequisites:** Stage 2.1A.3 (migration exists), Stage 2.1A.4 (container running), psycopg installed.

### Stage 2.1A.6 — Backup & Restore
**Deliverable:** `scripts/backup_postgres.ps1`, restore verification procedure.  
**Prerequisites:** Stage 2.1A.4 (container running), Stage 2.1A.5 (data present).

### Stage 2.1A.7 — SQLite Data Migration & Reconciliation
**Deliverable:** Extraction scripts, type conversion map, reconciliation report.  
**Prerequisites:** Stage 2.1A.5 (PostgreSQL schema applied), Stage 2.1A.6 (backup taken before migration).

### Stage 2.1A.8 — Cutover, Rollback & Final Acceptance
**Deliverable:** Cutover runbook, rollback procedure, final acceptance criteria.  
**Prerequisites:** All prior stages complete, backup verified, source write freeze executed.

---

## 6. Detailed Stage 2.1A.1 Analysis

### 6A. Configuration Architecture — Current State

**Authoritative source of database URL (verified by source inspection):**

1. **`backend/app/core/config.py` (Line 31–34):**
   ```python
   DATABASE_URL: str = Field(
       default=f"sqlite:///{BACKEND_DIR / 'oliver_dev.db'}",
       description="Database connection URL",
   )
   ```
   `Settings` is a `pydantic_settings.BaseSettings` subclass. It reads from:
   - Environment variables first (highest priority)
   - `.env` files defined in `model_config`:
     ```python
     env_file=(str(BACKEND_DIR / ".env"), str(BACKEND_DIR.parent / ".env")),
     ```
   - Defaults if neither is set.

2. **Resolution order (highest to lowest priority):**
   - `DATABASE_URL` environment variable in OS environment
   - `backend/.env` (file does not exist — skipped silently by pydantic-settings)
   - Root `.env` (exists; contains only desktop config — no `DATABASE_URL`)
   - Hardcoded default: `sqlite:///backend/oliver_dev.db`

3. **`backend/alembic.ini` (Line 8):**
   - `sqlalchemy.url = sqlite:///./backend/oliver_dev.db`
   - This static value is **overridden at runtime** by `backend/alembic/env.py` Line 37: `configuration["sqlalchemy.url"] = settings.DATABASE_URL`
   - Risk: `alembic` commands run without the full Python environment (e.g., `alembic upgrade head` without the app settings) would use the static SQLite URL. This must be documented as a known operational hazard.

4. **`backend/app/core/database.py` (Lines 12–22):**
   - Instantiates `engine` at module import time using `settings.DATABASE_URL`.
   - If `DATABASE_URL` is not set before import, the default SQLite value is used.
   - Stage 2.1A.0 `conftest.py` guard locks `os.environ["DATABASE_URL"]` before importing this module. ✅

5. **Conflicts identified:**
   - `alembic.ini` Line 8 static URL vs `settings.DATABASE_URL` runtime override — harmless in practice but confusing.
   - Root `.env` exists but contains no backend configuration. This is correct but might mislead developers into believing they need only one `.env`.

---

### 6B. Environment Separation Design

Minimum safe separation between environments:

| Environment | Backend DATABASE_URL | OLIVER_TEST_MODE | Method of Configuration |
|---|---|---|---|
| **Local development (SQLite)** | `sqlite:///./backend/oliver_dev.db` | Not set (not running tests) | `backend/.env` default |
| **Category A testing** | `sqlite:///:memory:` | `category_a` (explicit) | `OLIVER_TEST_MODE=category_a` env var before pytest; `DATABASE_URL` defaults to `:memory:` |
| **Docker local development** | `postgresql+psycopg://oliver_app_user:<pass>@localhost:5432/oliver_db` | Not set | `backend/.env` or Docker compose env injection |
| **Category B testing** | `postgresql+psycopg://oliver_test_user:<pass>@127.0.0.1:5432/oliver_test` | `category_b` (explicit) | Both vars set before pytest |
| **Future production** | `postgresql+psycopg://oliver_app_user:<pass>@db:5432/oliver_db` | Not applicable | Environment variable injection (never in `.env`) |

**Key design rule:** `DATABASE_URL` and `ENVIRONMENT` must be injected as environment variables for Docker, Compose, and production contexts. They must never be hardcoded in source files or committed to `.env`.

---

### 6C. Secret Management

For this Windows-local project, the recommended strategy is:

1. **Local development:** Store secrets in `backend/.env` (excluded from Git via `.gitignore`). The `.gitignore` already has `.env` and `.env.*` excluded (`!.env.example` preserved). ✅
2. **Docker Compose:** Inject secrets via Compose `environment:` section, reading from a local `.env` file at compose time. Never commit `.env` to Git.
3. **Secret rotation:** Requires updating `backend/.env` and restarting the service. No external secret manager needed for local development.
4. **Password exposure protection:**
   - `config.py` does not log `DATABASE_URL`. ✅ (Need to verify logger configuration does not log settings — assumed safe, unverified)
   - Stage 2.1A.0 `conftest.py` sanitizes all error messages. ✅
   - `alembic.ini` must not be edited to contain a real password — the runtime override in `env.py` prevents this.
5. **Windows Credential Manager:** Not recommended for this architecture. Environment variables via `.env` are simpler and consistent with the existing pydantic-settings approach.
6. **Git protection:** `.gitignore` already excludes `.env` and `.env.*`. Recommend `backend/.env.example` is kept current as the reference template.

**What must NEVER happen:**
- PostgreSQL passwords in source files or `alembic.ini`.
- Passwords in `DATABASE_URL` logged at startup or in error messages.
- `backend/.env` committed to Git.

---

### 6D. Host/Container Connection Architecture

This distinction is critical and commonly misunderstood:

| Context | Host for PostgreSQL | Correct URL |
|---|---|---|
| **FastAPI on Windows host → PostgreSQL container** | `localhost` or `127.0.0.1` (port forwarded from container) | `postgresql+psycopg://user:pass@localhost:5432/oliver_db` |
| **FastAPI inside Docker container → PostgreSQL container** | Service name in Compose network (e.g., `db`) | `postgresql+psycopg://user:pass@db:5432/oliver_db` |
| **pytest on Windows host → PostgreSQL container** | `localhost` or `127.0.0.1` | `postgresql+psycopg://oliver_test_user:pass@127.0.0.1:5432/oliver_test` |
| **pytest inside Docker container** | Service name | `postgresql+psycopg://oliver_test_user:pass@db:5432/oliver_test` |

**Why `localhost` changes meaning:** Inside a Docker container, `localhost` refers to the container's own loopback interface (`127.0.0.1` within the container's network namespace), not the host machine. The PostgreSQL container is a separate network peer. When running FastAPI or pytest **on the Windows host**, Docker Desktop exposes the container port to `localhost:5432` on the host, so `localhost` works. When running **inside a container**, the hostname must be the Docker Compose service name (e.g., `db`) which resolves via Docker's internal DNS to the PostgreSQL container's IP within the compose network.

**Practical implication for OLIVER 3.0:** Because FastAPI will initially be run on the Windows host (not inside a Docker container), `localhost:5432` is the correct host-side URL. The Docker Compose configuration should expose port 5432.

---

### 6E. SQLAlchemy Connection Configuration Recommendations

For a **local development single-process FastAPI** workload:

| Parameter | Recommended Value | Rationale |
|---|---|---|
| `pool_size` | `5` | Adequate for a single-user local backend with Ollama and UI clients. Keeps total connections manageable. |
| `max_overflow` | `10` | Allows burst connections (e.g., multiple device syncs) without exhausting PostgreSQL. `oliver_app_user` should have CONNECTION LIMIT 20. |
| `pool_timeout` | `30` | 30 seconds to wait for a connection before raising `TimeoutError`. Reasonable for local dev. |
| `pool_recycle` | `1800` | Recycle connections after 30 minutes to prevent stale connections from PostgreSQL's `idle_session_timeout`. |
| `pool_pre_ping` | `True` | Already present in `database.py` Line 20. Sends a lightweight `SELECT 1` before reusing a connection to detect dropped TCP connections. Essential for Docker restart scenarios. ✅ |
| Connection timeout | `connect_args={"connect_timeout": 10}` | Fail fast (10 seconds) if PostgreSQL is unreachable, rather than hanging indefinitely. |

**Current `database.py` has only `pool_pre_ping=True`.** The remaining parameters (`pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, `connect_args`) must be added in Stage 2.1A.1 implementation, conditioned on dialect:

```python
# Design proposal (Stage 2.1A.1 implementation — not yet implemented)
if settings.DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "connect_args": {"connect_timeout": 10},
    })
elif settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({
        "connect_args": {"check_same_thread": False},
    })
```

**Important:** Connection pooling parameters are invalid for SQLite (`StaticPool` or no pool). They must only be applied for PostgreSQL.

---

### 6F. Startup Failure Behavior

| Failure Condition | Current Behavior | Required Behavior (Stage 2.1A.1 Design) |
|---|---|---|
| PostgreSQL unreachable (stopped/starting) | SQLAlchemy raises `OperationalError` during `engine.connect()` in `_verify_startup_schema()`. Application fails closed with unhandled exception. | Catch `OperationalError` in `_verify_startup_schema()`. Log a clear message: "FATAL: PostgreSQL is unreachable at [host:port]. Ensure the database container is running." Then re-raise as `RuntimeError`. Do NOT fall back to SQLite. |
| Invalid credentials | `OperationalError` with authentication error | Same: catch, log sanitized message (no credentials), re-raise. |
| Database `oliver_db` missing | `OperationalError` during connect | Catch, log "FATAL: Database 'oliver_db' does not exist. Run provisioning before starting." Re-raise. |
| Schema missing (no alembic_version) | `RuntimeError("FATAL STARTUP BLOCKED: Database has no applied Alembic revisions...")` ✅ | Already handled by Stage 2.1A.0 implementation. |
| Migration outdated | `RuntimeError("FATAL STARTUP BLOCKED: Database revision does not match...")` ✅ | Already handled. |
| Insufficient permissions | `OperationalError` during connect or query | Catch, log sanitized message, re-raise. |
| Multiple migration heads | `RuntimeError("FATAL STARTUP BLOCKED: Multiple Alembic migration heads...")` ✅ | Already handled. |

**Absolute prohibition:** Automatic fallback to SQLite after PostgreSQL has been configured as the target database. The `_verify_startup_schema()` function already enforces this — unauthorized SQLite targets fail closed. ✅

---

### 6G. Stage 2.1A.0 Compatibility Assessment

The proposed Stage 2.1A.1 changes must not weaken any Stage 2.1A.0 safety controls.

| Control | Stage 2.1A.0 Implementation | Stage 2.1A.1 Risk | Mitigation |
|---|---|---|---|
| SQLite startup restriction | `_verify_startup_schema()` in `main.py` gates `create_all()` | Adding pool size params to `database.py` affects engine creation; must not bypass the dialect/path check. | Pool params are added based on `settings.DATABASE_URL` dialect, not by bypassing `_verify_startup_schema()`. |
| PostgreSQL migration verification | Alembic head check in `_verify_startup_schema()` | Adding `OperationalError` catching must not suppress the migration check. | Catch only network/auth errors; re-raise always. Never silently succeed. |
| Test URL isolation | `conftest.py` guard | Adding PostgreSQL pool params to `database.py` must not alter the validation rules. | Pool params are set at engine creation time, after URL validation. The validator checks the URL, not pool params. |
| Engine URL parity | `pytest_sessionstart()` checks `app_engine.url` | Adding params does not change `app_engine.url`. | ✅ Not affected. |
| Credential masking | Error paths sanitized | Error catch blocks for `OperationalError` must not log `str(exception)` which may contain the connection string. | Use `type(e).__name__` or fixed messages; never log `str(e)` for connection errors. |
| Fail-closed behavior | All unauthorized paths raise | `OperationalError` catching must re-raise, never swallow. | Always `raise RuntimeError(...) from e`. |

**Required compatibility adjustment:** When catching `OperationalError` in `_verify_startup_schema()`, the implementation must:
1. Log a sanitized message (no URL, no password).
2. `raise RuntimeError("FATAL STARTUP BLOCKED: ...") from e` — never return silently.

---

## 7. Alembic Configuration Issue (Critical Finding)

**Finding:** `backend/alembic.ini` Line 8 contains a hardcoded SQLite URL:
```ini
sqlalchemy.url = sqlite:///./backend/oliver_dev.db
```

**Why this matters:**
- If a developer runs `alembic upgrade head` without first setting `DATABASE_URL` in the environment, Alembic will use this hardcoded SQLite URL.
- This will apply PostgreSQL-only migrations to `backend/oliver_dev.db`, potentially corrupting the development database.
- `alembic/env.py` Lines 36–37 override this at runtime, but only when the full Python environment loads cleanly.

**Recommended fix for Stage 2.1A.1:** Update `alembic.ini` to remove the hardcoded URL and document that `DATABASE_URL` must always be set via environment before running Alembic. The `env.py` already has the correct runtime override. This is a configuration documentation fix, not a code change.

**Risk level:** Medium. No action needed before Stage 2.1A.1 planning, but must be addressed in the Stage 2.1A.1 implementation checklist.

---

## 8. Stage 2.1A.1 Implementation Scope

When authorized, Stage 2.1A.1 implementation is confined to:

**Files to create or modify:**
1. `backend/.env.example` — Add PostgreSQL URL template, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, pool settings.
2. `backend/app/core/database.py` — Add dialect-conditional pool configuration; add `connect_timeout` for PostgreSQL.
3. `backend/app/main.py` — Add `OperationalError` handling in `_verify_startup_schema()` for unreachable PostgreSQL; sanitized messages only; always re-raise.
4. `backend/alembic.ini` — Remove hardcoded SQLite URL; add comment requiring `DATABASE_URL` environment variable.
5. `docs/OLIVER_3_PHASE_2_1A1_IMPLEMENTATION_CHECKLIST.md` — Configuration checklist.

**Files NOT to touch:**
- `backend/tests/conftest.py` — No changes required.
- Any migration files — Stage 2.1A.3 handles these.
- Any database files — Protected.
- `.env` root — Desktop only.

---

## 9. Dependency and Readiness Matrix

| Stage | Prerequisites | Main Risks | Required Evidence Before Start | Ready? |
|---|---|---|---|---|
| **2.1A.1** | 2.1A.0 ✅ | Config drift, `alembic.ini` hardcoded URL, missing `backend/.env`, `OperationalError` leak | Configuration audit (this report) | **YES — READY** |
| **2.1A.2** | 2.1A.1 | Privilege/ownership errors, incorrect test role design, `oliver_migrator` vs `oliver_app_user` confusion | Finalized URL and environment design from 2.1A.1 | Blocked on 2.1A.1 |
| **2.1A.3** | 2.1A.2 | Incorrect schema migration, broken FK ordering, UUID type decision, SQLite dialect assumptions in migration | Reviewed role model; models fully inspected (done here) | Blocked on 2.1A.2 |
| **2.1A.4** | 2.1A.1, 2.1A.2, 2.1A.3 | Container data loss, volume deletion, Docker not installed, `localhost` vs service name confusion | Docker Desktop installed; role scripts ready; migration revision generated | **Blocked: Docker not installed** |
| **2.1A.5** | 2.1A.4 | Runtime/test failures, psycopg not installed, engine not connecting | Container running; psycopg installed; migration applied | **Blocked: Docker + psycopg not installed** |
| **2.1A.6** | 2.1A.4 | Unusable/unverified backups, missing checksums, PowerShell exit code errors | Container running with data | Blocked on 2.1A.4 |
| **2.1A.7** | 2.1A.3, 2.1A.5, 2.1A.6 | Data loss, FK violation order, UUID format mismatch, desktop vs backend SQLite confusion | Backup verified; PostgreSQL schema applied; SQLite source inspected | Blocked on upstream stages |
| **2.1A.8** | 2.1A.5, 2.1A.6, 2.1A.7 | Failed cutover, stale SQLite fallback, write divergence, mobile client incompatibility | All prior stages verified | Blocked on upstream stages |

---

## 10. Risk Assessment

| Risk ID | Description | Probability | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | Docker Desktop not installed — blocks all container stages | High (confirmed absent) | High | Must install before Stage 2.1A.4. No workaround. |
| R-02 | psycopg not installed — blocks all PostgreSQL connections | High (confirmed absent) | High | Install in Stage 2.1A.5. No earlier stages need it. |
| R-03 | `alembic.ini` hardcoded SQLite URL corrupts `oliver_dev.db` | Medium | High | Fix in Stage 2.1A.1. Remove hardcoded URL. |
| R-04 | `OperationalError` from unreachable PostgreSQL logs connection string | Medium | Medium | Catch specifically and log sanitized message in 2.1A.1. |
| R-05 | UUID stored as VARCHAR(36) causes performance issues at scale | Low | Low | Acceptable for local personal assistant. Document as known design choice. Future migration option exists. |
| R-06 | Messages table has dual FK (conversations + users) — Alembic must generate both | Medium | Medium | Verify by inspecting generated migration carefully in 2.1A.3. |
| R-07 | Missing `backend/.env` causes `DATABASE_URL` to default to SQLite unexpectedly | High | Medium | Create `backend/.env` from `.env.example` as first step of 2.1A.1. Document clearly. |
| R-08 | `localhost` vs container service name confusion during Docker development | Medium | Medium | Document connection URL matrix clearly (Section 6D of this report). |
| R-09 | SQLite-specific `PRAGMA foreign_keys=ON` event listener fires but is harmless on PostgreSQL | Low | Low | SQLite-only code path in `database.py` Lines 25–30 does not affect PostgreSQL. Acceptable. |

---

## 11. Prerequisites Checklist

The following must be true before Stage 2.1A.4 can begin:

- [ ] Docker Desktop installed and running on Windows host (WSL2 backend recommended)
- [ ] Docker Compose v2 available as `docker compose` subcommand
- [ ] `psycopg` (`psycopg[binary]` or `psycopg[c]`) installed in the Python environment
- [ ] `backend/.env` created from `.env.example` with all required values
- [ ] Stage 2.1A.1 configuration implemented
- [ ] Stage 2.1A.2 role design and scripts approved
- [ ] Stage 2.1A.3 initial Alembic migration generated and reviewed

---

## 12. Exact Stage 2.1A.1 Implementation Scope

**When authorized, Stage 2.1A.1 is strictly limited to:**

| File | Permitted Changes |
|---|---|
| `backend/.env.example` | Add PostgreSQL-related template variables |
| `backend/app/core/database.py` | Add dialect-conditional pool parameters; add `connect_timeout` for PostgreSQL |
| `backend/app/main.py` | Add `OperationalError` catching with sanitized re-raise in `_verify_startup_schema()` |
| `backend/alembic.ini` | Remove hardcoded `sqlalchemy.url`; add documenting comment |
| New doc: `docs/OLIVER_3_PHASE_2_1A1_IMPLEMENTATION_CHECKLIST.md` | Configuration checklist document |

**Explicitly excluded from Stage 2.1A.1:**
- Creating `docker-compose.yml`
- Creating PostgreSQL role SQL scripts
- Generating Alembic migrations
- Installing Docker or psycopg
- Creating `backend/.env` (this is an operator action, not an implementation action)
- Modifying `backend/tests/conftest.py`
- Connecting to any database
- Executing SQL

---

## 13. Acceptance Criteria for Stage 2.1A.1

Stage 2.1A.1 is complete when:

1. `backend/.env.example` contains all required PostgreSQL configuration variables.
2. `database.py` applies dialect-conditional connection pool parameters without breaking SQLite compatibility.
3. `main.py` catches `OperationalError` from unreachable PostgreSQL with a sanitized message and always re-raises as `RuntimeError`.
4. `alembic.ini` no longer contains a hardcoded database URL.
5. All 14 Category A tests are confirmed passing (`OLIVER_TEST_MODE=category_a pytest backend/tests/`).
6. Stage 2.1A.0 safety controls are verified unweakened by static code review.
7. No credentials appear in any error log path.
8. Neither `database/oliver.db` nor `backend/oliver_dev.db` is modified.

---

## 14. Unresolved Questions

| Question | Impact | Resolution Stage |
|---|---|---|
| Will FastAPI run on the Windows host or inside Docker? | Determines whether `localhost` or Docker service name is the correct PostgreSQL host in production. | Clarify before Stage 2.1A.4. Currently assumed: Windows host. |
| Should UUID columns be migrated to PostgreSQL native `UUID` type? | Affects the initial migration schema and future query performance. | Decide before Stage 2.1A.3. Recommendation: retain `VARCHAR(36)` initially; native UUID as a future optimization. |
| Should `preferences` column be migrated from `Text` to `JSONB`? | Affects indexability and query capability. | Decide before Stage 2.1A.3. Recommendation: retain `Text` initially for simplicity. |
| Should `psycopg[binary]` or `psycopg[c]` be installed? | Affects build requirements and cross-platform portability. | `psycopg[binary]` is recommended for Windows (no C compiler needed). Decide in Stage 2.1A.5. |
| Is Windows Credential Manager integration desired for PostgreSQL passwords? | Affects secret management complexity. | Low priority for local development. Standard `.env` approach is sufficient. |

---

## 15. Final Readiness Verdict

```
===========================================================================
STAGE 2.1A.1 READINESS VERDICT: READY WITH CONDITIONS

CONDITIONS:
1. Docker Desktop must be installed before Stage 2.1A.4 can be authorized.
2. psycopg must be installed before Stage 2.1A.5 can be authorized.
3. The alembic.ini hardcoded URL must be corrected as part of Stage 2.1A.1.
4. A backend/.env must be created by the operator (not automated) before
   any PostgreSQL-targeted startup.

Stage 2.1A.1 itself (configuration design only) has zero infrastructure 
prerequisites and may be authorized and implemented immediately.

Stages 2.1A.1 through 2.1A.8 each require separate explicit authorization.
===========================================================================
```

**STOPPING POINT.** No implementation performed. No files modified. Exactly one report created. Awaiting explicit user authorization before modifying any source file.
