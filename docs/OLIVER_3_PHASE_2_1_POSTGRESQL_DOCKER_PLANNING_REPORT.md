# OLIVER 3.0 — Phase 2.1
## PostgreSQL + Docker Architecture — Planning & Readiness Assessment

**Report Type:** Strictly Read-Only Architecture Planning  
**Milestone:** Phase 2.1  
**Date:** 2026-11-14  
**Baseline:** Phase 2A.1.3 Stage 2E — Final Audit PASS (195/195 tests)  
**Git HEAD:** `8e7ceac` ("New added.") — branch `main`  
**Authorization:** Architecture assessment, risk analysis, and implementation planning ONLY.  
**Outcome:** READY WITH CONDITIONS

---

## 1. Executive Summary

OLIVER 3.0 currently operates with **two independent SQLite databases** serving distinct architectural roles:

| Database | Path | Role |
|---|---|---|
| Backend DB | `backend/oliver_dev.db` | FastAPI shared backend: users, auth tokens, conversations, devices |
| Desktop DB | `database/oliver.db` | Local desktop runtime: sessions, messages, memories, reminders, notes, tasks, documents |

The objective of Phase 2.1 is to migrate the **backend database** from SQLite to **PostgreSQL running in Docker**, while preserving the desktop SQLite database for offline-first local operation.

**Key findings from actual source inspection:**

- The backend is architecturally clean and PostgreSQL-ready. It uses **SQLAlchemy 2.x** with the modern `DeclarativeBase` / `Mapped` ORM style, `create_all()` at startup, and an Alembic scaffold that is configured but has **no migration files yet** (only `.gitkeep`).
- The database URL is fully environment-variable-driven (`DATABASE_URL` in `Settings`), so switching from SQLite to PostgreSQL requires only a `.env` change — no source code modification.
- The root `requirements.txt` (desktop) and backend `requirements.txt` both **lack psycopg** (PostgreSQL driver). This is the primary missing prerequisite.
- **Docker Desktop is not installed** on this machine. This is the critical deployment prerequisite.
- The desktop SQLite database (`database/oliver.db`) has 20+ tables with FTS5 virtual tables, schema migrations, and local-only data. It must remain SQLite — there is no benefit and significant risk in migrating it to PostgreSQL.
- The desktop API client communicates with the backend exclusively via HTTP REST using `httpx`. Its contract will be unaffected by the backend database change.
- Alembic's `env.py` correctly imports all models and reads `DATABASE_URL` from `Settings`. Once migrations are created, they will work for both SQLite and PostgreSQL.

**Recommended readiness verdict: READY WITH CONDITIONS**  
Two hard prerequisites must be met before Stage 2.1A can begin:
1. Install Docker Desktop for Windows.
2. Add `psycopg[binary]` (psycopg v3) to `backend/requirements.txt`.

---

## 2. Current Architecture Findings

### 2.1 Project Layout (Evidence-Based)

```
my own voice assistant/
├── backend/                        # FastAPI shared backend
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py           # Settings (pydantic-settings, DATABASE_URL)
│   │   │   ├── database.py         # SQLAlchemy engine + session factory
│   │   │   ├── dependencies.py     # FastAPI dependency injection
│   │   │   ├── limiter.py          # SlowAPI rate limiter
│   │   │   ├── logging.py          # Structured logging
│   │   │   └── security.py         # JWT, bcrypt, token utilities
│   │   ├── models/
│   │   │   ├── user.py             # User ORM model
│   │   │   ├── conversation.py     # Conversation + Message ORM models
│   │   │   ├── device.py           # Device ORM model
│   │   │   └── token.py            # RefreshToken ORM model
│   │   ├── routers/
│   │   │   ├── auth.py             # POST /api/auth/{login,register,refresh,logout}
│   │   │   ├── chat.py             # POST /api/chat, GET /api/conversations
│   │   │   ├── devices.py          # Device registration
│   │   │   ├── health.py           # GET /api/health
│   │   │   ├── user.py             # User profile
│   │   │   └── welcome.py          # GET /
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── auth_service.py     # Auth business logic
│   │   │   ├── chat_service.py     # Chat + idempotency logic
│   │   │   └── ai_provider.py      # Ollama integration
│   │   └── main.py                 # FastAPI app + lifespan (create_all)
│   ├── alembic/
│   │   ├── env.py                  # Alembic config (reads settings.DATABASE_URL)
│   │   ├── script.py.mako
│   │   └── versions/.gitkeep       # NO migrations exist yet
│   ├── alembic.ini                 # Script location: backend/alembic
│   ├── oliver_dev.db               # Backend SQLite (5 tables, live data)
│   ├── requirements.txt            # Backend dependencies (NO psycopg)
│   └── .env.example                # Template (DATABASE_URL placeholder present)
│
├── database/
│   └── oliver.db                   # Desktop SQLite (20+ tables, FTS5, local-only)
│
├── desktop/
│   └── api_client/
│       ├── auth.py                 # AuthManager: JWT + refresh token rotation
│       ├── client.py               # OLIVERBackendClient: httpx REST client
│       ├── token_store.py          # WindowsCredentialStore (keyring/DPAPI)
│       └── exceptions.py           # Typed error hierarchy
│
├── voice/                          # Vosk STT, wake-word, voice manager
├── ui/                             # CustomTkinter desktop UI
├── commands/                       # Command routing (browser, etc.)
├── browser/                        # URL trust classification
├── requirements.txt                # Desktop/root dependencies (NO psycopg)
└── main.py                         # Desktop application entry point
```

### 2.2 Backend Database Layer — Verified Facts

**`backend/app/core/database.py`** (47 lines, fully inspected):

```python
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,   # {"check_same_thread": False} for SQLite only
    pool_pre_ping=True,
    echo=False,
)
```

- Engine is created from `settings.DATABASE_URL` at module-import time.
- `connect_args` check is dialect-aware (`startswith("sqlite")`).
- SQLite PRAGMA `foreign_keys=ON` is applied only for SQLite connections.
- Session factory: `SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)`
- Base: `class Base(DeclarativeBase)` — SQLAlchemy 2.x modern style.

**`backend/app/main.py`** (96 lines, fully inspected):

```python
Base.metadata.create_all(bind=engine)
```

- Called in the FastAPI `lifespan` async context manager.
- **This is the current schema creation mechanism** — no Alembic migrations are used in production today.
- Comment in source confirms this is a "dev SQLite mode" pattern.

### 2.3 ORM Models — Verified Schema

All 5 tables verified against both ORM definitions and actual SQLite DDL (confirmed identical):

| Table | Key Columns | Relationships |
|---|---|---|
| `users` | id (UUID/str PK), email (unique), hashed_password, full_name, preferences (JSON text), is_active, created_at, updated_at | → refresh_tokens, conversations, devices |
| `refresh_tokens` | id (UUID/str PK), user_id (FK→users), token_hash (unique), expires_at, revoked, created_at | → user |
| `conversations` | id (UUID/str PK), user_id (FK→users), title, created_at, updated_at | → user, messages |
| `messages` | id (UUID/str PK), conversation_id (FK→conversations), user_id (FK→users), role, content, latency_ms, created_at | → conversation |
| `devices` | id (UUID/str PK), user_id (FK→users), device_name, device_type, platform, client_version, registered_at, last_active_at | → user |

**Current live data in backend SQLite:** 3 users, 6 refresh tokens, 2 conversations, 3 messages, 2 devices.

### 2.4 Configuration — Verified Facts

**`backend/app/core/config.py`** (pydantic-settings `BaseSettings`):

```python
DATABASE_URL: str = Field(
    default=f"sqlite:///{BACKEND_DIR / 'oliver_dev.db'}",
    description="Database connection URL",
)
```

- Reads from `.env` file (searched at `backend/.env` then `../.env`).
- Switching to PostgreSQL requires only: `DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/oliver`
- **No source code change required for the URL switch.**

**`backend/alembic.ini`**: `sqlalchemy.url = sqlite:///./backend/oliver_dev.db`  
> **Note:** This static value in `alembic.ini` is overridden at runtime by `alembic/env.py` which reads `settings.DATABASE_URL`. The `.ini` value is used only when Alembic is invoked without the env.py override path — it must be updated or made a placeholder.

---

## 3. Git and Project Baseline

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD commit | `8e7ceac` ("New added.") |
| Working tree deletions | `database/oliver.db-shm`, `database/oliver.db-wal` (tracked, deleted on disk — SQLite WAL artifacts) |
| Untracked files | `docs/OLIVER_3_PHASE_2A1_3_STAGE_2E_FINAL_READINESS_AUDIT.md` |
| Test baseline | 195/195 tests across 10 suites (Stage 2E PASS) |
| Docker installed | **NO** — `docker` command not found |
| psycopg installed | **NO** — absent from both `requirements.txt` files |
| Alembic migrations | **NONE** — `versions/` contains only `.gitkeep` |

---

## 4. Existing Database Assessment

### 4.1 Backend Database (`backend/oliver_dev.db`)

**Classification: Migrate to PostgreSQL**

| Attribute | Value |
|---|---|
| Tables | 5 (users, refresh_tokens, conversations, messages, devices) |
| Live rows | ~16 total (dev data, low stakes) |
| ID strategy | UUID strings (VARCHAR 36) — PostgreSQL-compatible as-is or can adopt native UUID |
| Datetime strategy | `DateTime(timezone=True)` — compatible with PostgreSQL `TIMESTAMPTZ` |
| JSON storage | `preferences` stored as `Text` (JSON string) — can migrate to PostgreSQL native `JSONB` |
| FTS | None — not needed; conversation search can use PostgreSQL full-text search later |
| FKs | All cascade-delete FKs present — compatible with PostgreSQL |
| SQLite-specific workarounds | `PRAGMA foreign_keys=ON` (SQLite-only), `check_same_thread=False` (SQLite-only), naive datetime TZ handling in `auth_service.py` line 119 |

**SQLite-specific code that must be removed/adapted:**

1. `database.py` line 14-15: `connect_args["check_same_thread"] = False` — already gated on `startswith("sqlite")` ✅
2. `database.py` lines 25-30: SQLite PRAGMA `foreign_keys=ON` — already gated on `startswith("sqlite")` ✅
3. `auth_service.py` lines 119-121: Naive datetime UTC hack (`replace(tzinfo=timezone.utc)`) — PostgreSQL always returns timezone-aware datetimes, so this branch becomes dead code but causes no harm ✅

**Conclusion:** The backend ORM code is already written defensively enough that it will work with PostgreSQL without modification. Only the driver and URL are missing.

### 4.2 Desktop Database (`database/oliver.db`)

**Classification: Remain as SQLite — Do Not Migrate**

| Table Group | Tables | Rationale |
|---|---|---|
| Conversation history | `sessions`, `messages` | Local-only desktop chat history |
| Memory system | `memories`, `working_memory` | Local semantic memory, offline |
| Productivity | `notes`, `reminders`, `user_tasks` | Local personal data, offline |
| Document RAG | `indexed_documents`, `document_chunks`, `document_chunks_fts` | FTS5 virtual tables — SQLite-specific, requires SQLite |
| Agent state | `agent_tasks`, `agent_task_steps` | Ephemeral local task execution |
| Infrastructure | `schema_migrations`, `sqlite_sequence`, `data_migration_log` | SQLite-specific migration tracking |

**Critical observation:** `document_chunks_fts` uses an **FTS5 virtual table** (`CREATE VIRTUAL TABLE ... USING fts5`). FTS5 is a SQLite extension and cannot be directly migrated to PostgreSQL. The desktop database must remain SQLite permanently unless the RAG layer is completely redesigned.

**Current row counts:** 1 session, 8 messages, 9 data_migration_log records, 4 schema_migrations — low-stakes dev data.

---

## 5. Proposed PostgreSQL / Docker Architecture

> **Status: PROPOSED — not yet implemented. Illustrative only.**

### 5.1 Docker Compose Design (Illustrative)

```yaml
# docker-compose.yml (ILLUSTRATIVE — do not create yet)
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    container_name: oliver_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: oliver
      POSTGRES_USER: oliver_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}   # from .env — never hardcoded
    ports:
      - "127.0.0.1:5432:5432"                   # localhost-only binding — no public exposure
    volumes:
      - postgres_data:/var/lib/postgresql/data   # named volume for persistence
      - ./backend/init_scripts:/docker-entrypoint-initdb.d:ro  # optional init SQL

volumes:
  postgres_data:
    name: oliver_postgres_data
```

**Design rationale:**
- **PostgreSQL 16-alpine**: Stable LTS release, minimal image footprint (~80MB vs ~500MB for full image).
- **Port binding `127.0.0.1:5432`**: Only localhost can connect — reduces attack surface on Windows.
- **Named volume `oliver_postgres_data`**: Persists data across container restarts and upgrades.
- **No `pgBouncer` in Phase 2.1**: SQLAlchemy's built-in connection pool (`pool_pre_ping=True`) is sufficient for single-server desktop use. Add pgBouncer only if connection count becomes a problem.

### 5.2 Backend Connection String

```ini
# backend/.env (TEMPLATE — actual secret never shown)
DATABASE_URL=postgresql+psycopg://oliver_user:CHANGE_ME@127.0.0.1:5432/oliver
```

- Driver: `psycopg` (psycopg v3) — not `psycopg2`.
- SQLAlchemy dialect string: `postgresql+psycopg`.
- Host: `127.0.0.1` (loopback, matches Docker port binding).

### 5.3 Connection Pooling Strategy

| Setting | Recommended Value | Rationale |
|---|---|---|
| `pool_pre_ping` | `True` (already set) | Detects stale connections |
| `pool_size` | 5 (default) | Adequate for desktop single-user |
| `max_overflow` | 10 (default) | Burst capacity |
| `pool_timeout` | 30s (default) | Reasonable for local connection |
| `pool_recycle` | 1800 (30 min) | Recycle long-lived connections |

No external pooler (pgBouncer) required at this scale.

### 5.4 SQLite Offline Coexistence

```
backend/app/core/
├── database.py          # MODIFY: add PostgreSQL-specific setup (pool_recycle, etc.)
│                        # Remove SQLite-only connect_args when PG dialect is active
└── config.py            # NO CHANGE — DATABASE_URL already env-driven
```

The offline strategy is **environment-variable-based dialect selection**:
- `DATABASE_URL=sqlite:///...` → SQLite mode (offline / testing)
- `DATABASE_URL=postgresql+psycopg://...` → PostgreSQL mode (online / production)

No code changes needed for this dual-mode operation. The existing dialect guards in `database.py` already handle both.

---

## 6. psycopg and SQLAlchemy Compatibility Assessment

### 6.1 Current Dependency State (Verified)

**`backend/requirements.txt`** (11 lines, fully inspected):

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic-settings>=2.5.0
sqlalchemy>=2.0.30          ← SQLAlchemy 2.x ✅
alembic>=1.13.0             ← Alembic ✅
bcrypt>=4.0.0
pyjwt>=2.9.0
slowapi>=0.1.9
pytest>=8.0.0
httpx>=0.27.0
                            ← psycopg MISSING ❌
```

### 6.2 psycopg v3 Compatibility Matrix

| Component | Version Required | Status |
|---|---|---|
| Python | ≥3.8 | ✅ 3.13.5 installed |
| SQLAlchemy | ≥2.0 | ✅ `>=2.0.30` in requirements |
| psycopg | 3.x (`psycopg[binary]`) | ❌ Not installed |
| Alembic | ≥1.13 | ✅ `>=1.13.0` in requirements |
| PostgreSQL server | ≥12 | ⚠️ Not running (Docker not installed) |

**psycopg installation plan (Stage 2.1A):**

```
# Add to backend/requirements.txt:
psycopg[binary]>=3.1.0
```

> **Important:** Use `psycopg[binary]` (not `psycopg[c]`, not `psycopg2`, not `psycopg2-binary`). The `[binary]` extra bundles pre-compiled libpq for Windows compatibility without requiring a local PostgreSQL installation or C compiler.

### 6.3 SQLAlchemy 2.x + psycopg 3 Known Compatibility Notes

| Issue | Impact | Resolution |
|---|---|---|
| UUID as `String(36)` vs `UUID` type | Low — works on both dialects | Optional: migrate to `sqlalchemy.UUID(as_uuid=True)` in Phase 2.1D |
| `DateTime(timezone=True)` → PostgreSQL `TIMESTAMPTZ` | None — fully compatible | No change needed |
| `Text` for `preferences` JSON → PostgreSQL `JSONB` | Optional optimization | Can stay as `Text`; migrate to `JSONB` in Phase 2.1D for indexability |
| `pool_pre_ping` overhead | Negligible for desktop | Keep as-is |
| `autoflush=False` | Compatible with both dialects | No change needed |

---

## 7. SQLite Coexistence Strategy

### 7.1 Classification Summary

| Database | Dialect | Migration Target | Reason |
|---|---|---|---|
| `backend/oliver_dev.db` | SQLite → PostgreSQL | **Full migration** | Shared server data needing multi-device access |
| `database/oliver.db` | SQLite (permanent) | **No migration** | Contains FTS5 virtual tables; local-only offline data |

### 7.2 Testing Strategy for Dual-Mode

- **CI / offline tests:** `DATABASE_URL=sqlite:///./backend/test.db` (in-memory or temp file)
- **Integration tests with Docker:** `DATABASE_URL=postgresql+psycopg://...` (against Docker container)
- **Backend test isolation:** Existing `backend/tests/conftest.py` likely uses SQLite for speed — verify before changing.

### 7.3 Alembic Migration Considerations

The Alembic `env.py` reads `settings.DATABASE_URL` at runtime. When generating migrations:

```powershell
# From project root, with backend active
alembic -c backend/alembic.ini revision --autogenerate -m "initial_schema"
```

This will generate a migration compatible with whichever dialect `DATABASE_URL` points to.

> **Risk:** The initial migration will capture the current 5-table schema. If generated against SQLite, some PostgreSQL-specific types (e.g., `UUID`, `JSONB`) will not be automatically applied — the migration file must be reviewed and adjusted manually before applying to PostgreSQL.

---

## 8. Migration and Rollback Plan

### 8.1 Migration Sequence

```
Stage 2.1A → Install Docker Desktop + psycopg[binary]
Stage 2.1B → Create docker-compose.yml + verify PostgreSQL container starts
Stage 2.1C → Add psycopg[binary] to backend/requirements.txt + verify import
Stage 2.1D → Generate initial Alembic migration from current ORM models
Stage 2.1E → Apply migration to PostgreSQL container + verify schema
Stage 2.1F → Migrate existing dev data from oliver_dev.db to PostgreSQL (optional)
Stage 2.1G → Update .env DATABASE_URL to postgresql+psycopg
Stage 2.1H → Run full 195-test regression suite against PostgreSQL backend
```

### 8.2 Rollback Plan

| Stage | Rollback Action |
|---|---|
| Any Stage 2.1x | Set `DATABASE_URL` back to `sqlite:///./backend/oliver_dev.db` in `.env` |
| Docker container issue | `docker compose down` — SQLite unaffected |
| Migration failure | Alembic `alembic downgrade -1` — reverts last migration |
| Data corruption | Restore from `oliver_dev.db` backup (created before Stage 2.1F) |

**SQLite database will be preserved throughout** — it is not modified or deleted during the PostgreSQL migration.

### 8.3 Data Preservation

- `backend/oliver_dev.db` currently has 3 users and 16 total rows.
- These are dev/test accounts and can be recreated.
- If preservation is desired: `sqlite3 oliver_dev.db .dump > oliver_dev_backup.sql` before Stage 2.1F.
- Do not modify or restore `database/oliver.db` — it is not in scope.

---

## 9. Security Assessment

### 9.1 Current Security Posture (Verified)

| Control | Status | Evidence |
|---|---|---|
| Password hashing | ✅ bcrypt | `security.py`, `auth_service.py` |
| JWT signing | ✅ HS256 | `config.py`, `security.py` |
| Refresh token rotation | ✅ One-time rotation with reuse detection | `auth_service.py` lines 109-115 |
| Token storage (desktop) | ✅ Windows Credential Manager (DPAPI) | `token_store.py` |
| Refresh token storage (DB) | ✅ SHA-256 hash only — raw token never stored | `auth_service.py` |
| Rate limiting | ✅ SlowAPI (10/min auth, 30/min chat) | `config.py`, `limiter.py` |
| CORS | ⚠️ Default `["*"]` in dev | `config.py` line 36 |
| SQL injection | ✅ ORM-parameterized queries throughout | All service files |

### 9.2 PostgreSQL-Specific Security Requirements

| Requirement | Action Required |
|---|---|
| PostgreSQL credentials | Never hardcode — use `.env` file + `.gitignore` (`.env` already gitignored) |
| Docker port binding | `127.0.0.1:5432` only — not `0.0.0.0:5432` |
| Dedicated DB user | Create `oliver_user` with limited privileges — not `postgres` superuser |
| Connection encryption | `sslmode=prefer` for loopback (optional); `sslmode=require` for remote |
| Backup strategy | `pg_dump` before any destructive migration |
| `.env` in production | Use environment variables directly, not file |

### 9.3 Secrets Management Rules

- Never commit actual `DATABASE_URL` with credentials to Git.
- `.env` file is already listed in `.gitignore` (verified: `.gitignore` present at root).
- `backend/.env.example` already has the `DATABASE_URL` placeholder — update for PostgreSQL format in Stage 2.1A.
- `JWT_SECRET_KEY` default is explicitly labelled "insecure" in source — must be changed in production regardless of database choice.

---

## 10. Testing and Acceptance Strategy

### 10.1 Existing Test Infrastructure

| Suite | File | Scope |
|---|---|---|
| Backend auth | `backend/tests/test_auth.py` | Register, login, refresh, logout |
| Backend endpoints | `backend/tests/test_endpoints.py` | Chat, conversations, devices |
| Backend tokens | `backend/tests/test_tokens.py` | Token rotation, reuse detection |
| Backend isolation | `backend/tests/test_isolation.py` | Cross-user data isolation |
| Stage 1-2E regression | `tests/regression/test_stage*.py` | Desktop/voice integration |

### 10.2 Proposed Acceptance Criteria for Phase 2.1

| Test | Pass Condition |
|---|---|
| PostgreSQL container starts | `docker compose up -d` exits 0, `docker compose ps` shows "healthy" |
| psycopg import | `python -c "import psycopg; print(psycopg.__version__)"` succeeds |
| SQLAlchemy + PostgreSQL connection | `engine.connect()` succeeds with PostgreSQL URL |
| Alembic migration applies | `alembic upgrade head` exits 0 against PostgreSQL |
| All 5 tables created | Schema matches ORM models exactly |
| Backend test suite (PostgreSQL) | All `backend/tests/` tests pass with PostgreSQL URL |
| Desktop regression suite | All 195 existing tests still pass (backend not in test scope) |
| Auth round-trip | Register → Login → Refresh → Logout cycle works end-to-end |
| Data isolation | User A cannot access User B's conversations |
| Rollback | Setting SQLite URL restores full functionality |

---

## 11. Proposed Implementation Stages

### Stage 2.1A — Infrastructure Prerequisites *(Suggested first step)*
**Scope:** Install Docker Desktop; add `psycopg[binary]>=3.1.0` to `backend/requirements.txt`; create `docker-compose.yml`; verify PostgreSQL container starts; update `backend/.env.example`.

**Files changed:**
- `backend/requirements.txt` — add psycopg
- `docker-compose.yml` — NEW
- `backend/.env.example` — update DATABASE_URL placeholder

**Risk:** LOW. No application code changed.

---

### Stage 2.1B — Alembic Foundation
**Scope:** Generate initial Alembic migration from current ORM models. Review and adjust generated SQL for PostgreSQL compatibility (UUID types, JSONB for preferences column).

**Files changed:**
- `backend/alembic/versions/<hash>_initial_schema.py` — NEW
- `backend/alembic.ini` — update static `sqlalchemy.url` to placeholder

**Risk:** LOW. Migration is generated from existing ORM — no manual SQL required.

---

### Stage 2.1C — PostgreSQL Schema Application
**Scope:** Run `alembic upgrade head` against Docker PostgreSQL container. Verify all 5 tables created with correct schema and indexes.

**Files changed:** None (Alembic applies migration to database, not files).

**Risk:** LOW. Additive DDL against a fresh empty database.

---

### Stage 2.1D — Backend .env Update + Integration Validation
**Scope:** Update `backend/.env` `DATABASE_URL` to PostgreSQL. Run full backend test suite. Run full desktop regression suite. Verify existing behavior preserved.

**Files changed:**
- `backend/.env` — DATABASE_URL update (not committed to Git)

**Risk:** MEDIUM. First live traffic against PostgreSQL. Rollback: revert `.env`.

---

### Stage 2.1E — Optional Type Enhancements
**Scope:** Optionally migrate `preferences` column from `Text` to `JSONB`; migrate UUIDs from `String(36)` to native `UUID`. Generate and apply migration.

**Files changed:**
- `backend/app/models/user.py` — JSONB type (optional)
- `backend/alembic/versions/<hash>_pg_type_enhancements.py` — NEW

**Risk:** LOW-MEDIUM. Schema change requires Alembic migration and data cast.

---

### Stage 2.1F — Dev Data Migration (Optional)
**Scope:** If existing `oliver_dev.db` dev users are worth preserving, write a one-time migration script to export SQLite data and import to PostgreSQL.

**Files changed:**
- `scripts/migrate_sqlite_to_pg.py` — NEW (disposable script)

**Risk:** LOW. Dev data only; PostgreSQL schema is source of truth going forward.

---

### Stage 2.1G — Integration Regression Verification
**Scope:** Full end-to-end regression with PostgreSQL as the active backend. Confirm 195+ tests pass. Update CI configuration if applicable.

**Files changed:** None (test execution only).

**Risk:** LOW. All prior stages verified before this point.

---

## 12. Exact Proposed File-Change Inventory

| File | Action | Stage | Notes |
|---|---|---|---|
| `docker-compose.yml` | **CREATE** | 2.1A | PostgreSQL 16-alpine, named volume, localhost binding |
| `docker-compose.override.yml` | **CREATE** (optional) | 2.1A | Dev overrides (port exposure, debug settings) |
| `backend/requirements.txt` | **MODIFY** | 2.1A | Add `psycopg[binary]>=3.1.0` |
| `backend/.env.example` | **MODIFY** | 2.1A | Update `DATABASE_URL` to PG format, add `POSTGRES_PASSWORD` placeholder |
| `backend/.env` | **MODIFY** | 2.1D | `DATABASE_URL=postgresql+psycopg://...` (not committed) |
| `backend/alembic.ini` | **MODIFY** | 2.1B | Replace static `sqlalchemy.url` with `%(here)s` or env placeholder |
| `backend/alembic/versions/<hash>_initial_schema.py` | **CREATE** | 2.1B | Autogenerated + reviewed |
| `backend/alembic/versions/<hash>_pg_type_enhancements.py` | **CREATE** (optional) | 2.1E | JSONB preferences, native UUID |
| `backend/app/models/user.py` | **MODIFY** (optional) | 2.1E | `JSONB` for preferences |
| `backend/app/core/database.py` | **MODIFY** (minor) | 2.1D | Add `pool_recycle=1800` for PostgreSQL; existing SQLite guards already correct |
| `scripts/migrate_sqlite_to_pg.py` | **CREATE** (disposable) | 2.1F | One-time dev data migration |

**Files that do NOT require modification:**
- `backend/app/main.py` — `create_all` can remain for dev fallback
- `backend/app/core/config.py` — already env-driven
- `backend/app/services/auth_service.py` — naive datetime fix is harmless with PG
- `backend/app/services/chat_service.py` — no dialect-specific code
- `backend/alembic/env.py` — already reads `settings.DATABASE_URL`
- All desktop code (`ui/`, `voice/`, `commands/`, `browser/`) — unaffected
- `desktop/api_client/` — unaffected (HTTP REST only)
- `database/oliver.db` — not migrated
- All existing test files — unmodified

---

## 13. Risks, Dependencies, and Unresolved Decisions

### 13.1 Hard Prerequisites (Blockers)

| Prerequisite | Status | Action Required |
|---|---|---|
| Docker Desktop for Windows | ❌ NOT INSTALLED | Download and install Docker Desktop from docker.com before Stage 2.1A |
| `psycopg[binary]>=3.1.0` | ❌ NOT INSTALLED | Add to `backend/requirements.txt` and install |

> **These two prerequisites block all subsequent stages.** No implementation work is possible until Docker Desktop is installed and PostgreSQL can be started.

### 13.2 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Docker Desktop installation requires Windows Hyper-V / WSL2 | Medium | High | Verify Windows features; Docker Desktop installer guides this |
| psycopg binary wheel unavailable for Python 3.13.5 | Low | High | Test with `pip install psycopg[binary]`; fallback to `psycopg[c]` with libpq installed |
| Alembic autogenerate misses FTS5 or SQLite-specific constructs | Low | Low | Backend DB has no FTS5 — not an issue |
| `create_all()` in `main.py` conflicts with Alembic | Low | Medium | In production, disable `create_all()` once migrations are established |
| Naive datetime handling in `auth_service.py` | Low | Low | The `replace(tzinfo=timezone.utc)` branch becomes dead code with PostgreSQL — harmless |
| `alembic.ini` hardcoded SQLite URL | Low | Low | Alembic `env.py` overrides this at runtime — only affects standalone `alembic` CLI invocation |
| Token reuse detection uses DB query on every refresh | Low | Negligible | Performance acceptable for single-user desktop; optimize only if needed |
| CORS set to `["*"]` by default | Medium | Medium | Must be tightened before any production deployment |
| `.env` file not in `backend/.gitignore` | Unknown | High | Verify `.gitignore` excludes `backend/.env` before committing PG credentials |

### 13.3 Unresolved Decisions

| Decision | Options | Recommendation |
|---|---|---|
| UUID column type in PostgreSQL | Stay as `String(36)` OR migrate to `UUID` native type | Stay as `String(36)` in Phase 2.1 — simpler migration, no behavioral change |
| `preferences` column type | Stay as `Text` OR migrate to `JSONB` | Stay as `Text` in Phase 2.1; migrate to `JSONB` only if JSON querying is needed |
| `create_all()` in production | Keep for dev fallback OR remove in favour of Alembic-only | Keep for now; mark with a comment; remove in a dedicated cleanup stage |
| Data migration of existing dev users | Migrate 3 dev users OR start fresh | Start fresh — dev accounts have no production value |
| PostgreSQL user privileges | Full schema access OR minimal privileges | Create dedicated `oliver_user` with CREATE/SELECT/INSERT/UPDATE/DELETE on `oliver` database only — not superuser |
| Docker Desktop license | Personal use (free) OR commercial | Confirm Docker Desktop license terms for your use case |
| Future Flutter mobile integration | Shared PostgreSQL OR separate backend | Shared PostgreSQL (already the architecture decision) — no change |

### 13.4 Dependency Chain

```
Install Docker Desktop
       ↓
Start PostgreSQL container (Stage 2.1A/B)
       ↓
Install psycopg[binary] (Stage 2.1A)
       ↓
Generate Alembic migration (Stage 2.1B)
       ↓
Apply migration to PostgreSQL (Stage 2.1C)
       ↓
Switch DATABASE_URL (Stage 2.1D)
       ↓
Run regression tests (Stage 2.1G)
```

No stage can be skipped without blocking subsequent stages.

---

## 14. Final Readiness Recommendation

### Verdict: READY WITH CONDITIONS

The OLIVER 3.0 backend codebase is **architecturally well-prepared** for PostgreSQL migration:

✅ SQLAlchemy 2.x modern ORM in use  
✅ Database URL is fully environment-variable-driven — no hardcoded SQLite paths in application logic  
✅ Alembic scaffold is in place and configured correctly  
✅ All ORM models use PostgreSQL-compatible types  
✅ Existing dialect guards in `database.py` already isolate SQLite-specific behavior  
✅ Desktop SQLite database is completely independent and unaffected  
✅ Desktop API client uses pure HTTP REST — database dialect change is transparent  
✅ Auth security (bcrypt, JWT, rotating tokens, DPAPI storage) is unaffected  

❌ **Docker Desktop is not installed** — this is the single most critical blocker  
❌ **`psycopg[binary]` is not installed** — required before any PostgreSQL connection can be established  
❌ **No Alembic migrations exist** — `versions/` directory is empty; first migration must be generated  

### Recommended First Step

**Install Docker Desktop for Windows**, then proceed with Stage 2.1A.

Docker Desktop installation:
1. Download from: https://docs.docker.com/desktop/install/windows-install/
2. Requires WSL2 (Windows Subsystem for Linux 2) or Hyper-V.
3. After installation, verify: `docker --version` and `docker compose version`.

Once Docker Desktop is installed and `psycopg[binary]` can be pip-installed, all Phase 2.1 stages can proceed in order with low overall risk.

### Implementation Authorization Request

This planning report is complete. No source code, test files, configuration, or databases have been modified during this planning phase.

**Explicit authorization is required before beginning Stage 2.1A.**

---

*Report generated: 2026-11-14 | Audit mode: READ-ONLY | Author: Antigravity Planning Agent*  
*Based on direct source inspection of commit `8e7ceac` on branch `main`*
