# OLIVER 3.0 — Stage 2.1A.3 Initial Alembic Migration Readiness & Planning Audit

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A3_INITIAL_ALEMBIC_MIGRATION_READINESS_REPORT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Migration  
**Stage:** 2.1A.3 — Initial Alembic Migration (Readiness & Technical Planning Audit)  
**Audit Date:** 2026-11-22  
**Audit Mode:** STRICTLY READ-ONLY — Zero code modifications, zero database operations  
**Baseline Git Commit:** `8f1cc57` ("Stage 2.1A.2: PostgreSQL roles and permissions security")  
**Preceding Reference:** `docs/OLIVER_3_PHASE_2_1A2_DEF01_FIX_REPORT.md`

---

## 1. Executive Summary

This report establishes a comprehensive, evidence-based technical specification and readiness assessment for **Stage 2.1A.3 — Initial Alembic Migration**.

### Audit Verdict: **READY WITH CONDITIONS**

1. **Model & Schema Definition is Complete:** All 5 SQLAlchemy ORM models (`users`, `conversations`, `messages`, `refresh_tokens`, `devices`) in `backend/app/models/` have been surveyed down to every column, type, foreign key cascade, unique constraint, and index.
2. **SQLite Database Boundaries are Verified:** 
   - `database/oliver.db` (192,512 bytes) is the **desktop client local AI/RAG/task database** (12 tables including `agent_tasks`, `document_chunks`, `memories`, `reminders`). It has its own integer-version `schema_migrations` table and **must NEVER be migrated to PostgreSQL**.
   - `backend/oliver_dev.db` (94,208 bytes) is the **backend development database** containing 5 tables populated by SQLAlchemy's `create_all()`. It holds 3 test users, 2 conversations, 3 messages, 6 refresh tokens, and 2 devices. No Alembic version table exists. Data migration from `oliver_dev.db` is a separate, future stage (Stage 2.1A.7).
3. **Alembic Infrastructure is Verified:** `backend/alembic/env.py` (committed in `8f1cc57`) enforces fail-closed migration credential resolution via `MIGRATION_DATABASE_URL` using `python-dotenv` (`dotenv_values()`). It never falls back to `settings.DATABASE_URL` or SQLite.
4. **PostgreSQL Role & Privilege Alignment is Verified:** `backend/scripts/init_postgres.sh` (committed in `8f1cc57`) assigns database and schema ownership to `oliver_migrator`, revokes `CONNECT` on `oliver_db` from `PUBLIC`, and declares `ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user`.
5. **Stage 2.1A.3 Scope Separation (The Core Condition):**
   - Live migration autogeneration (`alembic revision --autogenerate`) and migration execution (`alembic upgrade head`) require a live PostgreSQL instance and `psycopg` driver (blocked on Docker installation).
   - However, the initial migration can be **deterministically and statically authored offline** in Stage 2.1A.3 directly from `Base.metadata`.
   - Authoring the initial migration revision file satisfies `backend/app/main.py:76-84` (`script_dir.get_heads()`), moving the repository to a state where an Alembic revision head exists.
   - **Applying** the migration against the live database is deferred to Stage 2.1A.4/2.1A.5 when the Docker container is running.

---

## 2. Repository Baseline & Git State

### 2.1 Git Status
- **Active Branch:** `main`
- **HEAD Commit:** `8f1cc576f4d48a50068445caeab97766ae63ad20`
- **Commit Subject:** `Stage 2.1A.2: PostgreSQL roles and permissions security`
- **Working Tree:** Completely clean (`nothing to commit, working tree clean`).

### 2.2 Database File Integrity
- `database/oliver.db`: 192,512 bytes, Last Modified 07-11-2026 19:38:26 — **INTACT**
- `backend/oliver_dev.db`: 94,208 bytes, Last Modified 07-11-2026 18:12:44 — **INTACT**

---

## 3. Model & Schema Inventory

Inspection of all files in `backend/app/models/` reveals exactly 5 SQLAlchemy 2.0 mapped models:

```
           ┌──────────┐
           │  users   │
           └────┬─────┘
       ┌────────┼────────┬────────┐
       ▼        ▼        ▼        ▼
┌──────────────┐│ ┌────────────┐┌─────────┐
│conversations ││ │refresh_toks││ devices │
└──────┬───────┘│ └────────────┘└─────────┘
       │        │
       ▼        ▼
    ┌──────────────┐
    │   messages   │ (Dual FK: conversations.id + users.id)
    └──────────────┘
```

### 3.1 Table: `users`
**Source:** `backend/app/models/user.py`

| Column | SQLAlchemy Type | PostgreSQL Type | Nullable | Constraints & Defaults | Notes |
|---|---|---|---|---|---|
| `id` | `String(36)` | `VARCHAR(36)` | No | PK, `default=uuid.uuid4` | Python-side UUID generation |
| `email` | `String(255)` | `VARCHAR(255)` | No | UNIQUE, index | Case-insensitive in logic |
| `hashed_password` | `String(255)` | `VARCHAR(255)` | No | None | Argon2 / Passlib hash |
| `full_name` | `String(255)` | `VARCHAR(255)` | No | `default="OLIVER User"` | Display name |
| `preferences` | `Text` | `TEXT` | No | `default='{"theme": ...}'` | JSON stored as TEXT |
| `is_active` | `Boolean` | `BOOLEAN` | No | `default=True` | Active status |
| `created_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `default=datetime.now(utc)` | UTC timezone aware |
| `updated_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `onupdate=datetime.now(utc)` | UTC timezone aware |

- **Indexes:**
  - `ix_users_id` on `users(id)`
  - `ix_users_email` (UNIQUE) on `users(email)`
- **Relationships:**
  - `refresh_tokens`: cascade `"all, delete-orphan"`
  - `conversations`: cascade `"all, delete-orphan"`
  - `devices`: cascade `"all, delete-orphan"`

---

### 3.2 Table: `conversations`
**Source:** `backend/app/models/conversation.py`

| Column | SQLAlchemy Type | PostgreSQL Type | Nullable | Constraints & Defaults | Notes |
|---|---|---|---|---|---|
| `id` | `String(36)` | `VARCHAR(36)` | No | PK, `default=uuid.uuid4` | Python-side UUID |
| `user_id` | `String(36)` | `VARCHAR(36)` | No | FK(`users.id`, CASCADE), index | Owner user |
| `title` | `String(255)` | `VARCHAR(255)` | No | `default="New Chat"` | Conversation title |
| `created_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `default=datetime.now(utc)` | UTC aware |
| `updated_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `onupdate=datetime.now(utc)` | UTC aware |

- **Indexes:**
  - `ix_conversations_id` on `conversations(id)`
  - `ix_conversations_user_id` on `conversations(user_id)`
- **Relationships:**
  - `user`: back_populates `"conversations"`
  - `messages`: cascade `"all, delete-orphan"`, order_by `"Message.created_at"`

---

### 3.3 Table: `messages`
**Source:** `backend/app/models/conversation.py`

| Column | SQLAlchemy Type | PostgreSQL Type | Nullable | Constraints & Defaults | Notes |
|---|---|---|---|---|---|
| `id` | `String(36)` | `VARCHAR(36)` | No | PK, `default=uuid.uuid4` | Python-side UUID |
| `conversation_id` | `String(36)` | `VARCHAR(36)` | No | FK(`conversations.id`, CASCADE), index | Parent chat session |
| `user_id` | `String(36)` | `VARCHAR(36)` | No | FK(`users.id`, CASCADE), index | Direct user reference |
| `role` | `String(50)` | `VARCHAR(50)` | No | None | `"user"`, `"assistant"`, `"system"` |
| `content` | `Text` | `TEXT` | No | None | Message content |
| `latency_ms` | `Float` | `FLOAT` / `DOUBLE PRECISION` | **Yes** | None | Model inference latency |
| `created_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `default=datetime.now(utc)` | UTC aware |

- **Indexes:**
  - `ix_messages_id` on `messages(id)`
  - `ix_messages_conversation_id` on `messages(conversation_id)`
  - `ix_messages_user_id` on `messages(user_id)`
- **Special Dependency:** Dual foreign keys! Must be created after both `users` and `conversations`.

---

### 3.4 Table: `refresh_tokens`
**Source:** `backend/app/models/token.py`

| Column | SQLAlchemy Type | PostgreSQL Type | Nullable | Constraints & Defaults | Notes |
|---|---|---|---|---|---|
| `id` | `String(36)` | `VARCHAR(36)` | No | PK, `default=uuid.uuid4` | Python-side UUID |
| `user_id` | `String(36)` | `VARCHAR(36)` | No | FK(`users.id`, CASCADE), index | Target user |
| `token_hash` | `String(64)` | `VARCHAR(64)` | No | UNIQUE, index | SHA-256 hex string |
| `expires_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | None | Expiration timestamp |
| `revoked` | `Boolean` | `BOOLEAN` | No | `default=False` | One-time token rotation |
| `created_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `default=datetime.now(utc)` | UTC aware |

- **Indexes:**
  - `ix_refresh_tokens_id` on `refresh_tokens(id)`
  - `ix_refresh_tokens_user_id` on `refresh_tokens(user_id)`
  - `ix_refresh_tokens_token_hash` (UNIQUE) on `refresh_tokens(token_hash)`

---

### 3.5 Table: `devices`
**Source:** `backend/app/models/device.py`

| Column | SQLAlchemy Type | PostgreSQL Type | Nullable | Constraints & Defaults | Notes |
|---|---|---|---|---|---|
| `id` | `String(36)` | `VARCHAR(36)` | No | PK, `default=uuid.uuid4` | Python-side UUID |
| `user_id` | `String(36)` | `VARCHAR(36)` | No | FK(`users.id`, CASCADE), index | Owning user |
| `device_name` | `String(255)` | `VARCHAR(255)` | No | None | e.g. "Laptop", "Pixel 9" |
| `device_type` | `String(50)` | `VARCHAR(50)` | No | `default="desktop"` | "desktop", "mobile", "web" |
| `platform` | `String(50)` | `VARCHAR(50)` | No | `default="windows"` | "windows", "android", "ios" |
| `client_version` | `String(50)` | `VARCHAR(50)` | No | `default="3.0.0"` | Client version |
| `registered_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `default=datetime.now(utc)` | Registration UTC |
| `last_active_at` | `DateTime(timezone=True)` | `TIMESTAMPTZ` | No | `onupdate=datetime.now(utc)` | Activity timestamp |

- **Indexes:**
  - `ix_devices_id` on `devices(id)`
  - `ix_devices_user_id` on `devices(user_id)`

---

## 4. SQLite Database Comparison & Separation Audit

A safe, strictly read-only inspection (via Python `sqlite3` using URI `mode=ro`) confirmed the following architecture:

### 4.1 Desktop SQLite Database (`database/oliver.db`)
- **File Size:** 192,512 bytes
- **Role:** Dedicated offline local database for the Windows CustomTkinter desktop assistant.
- **Tables (12):**
  - `agent_tasks` (0 rows)
  - `agent_task_steps` (0 rows)
  - `data_migration_log` (9 rows)
  - `document_chunks` (0 rows)
  - `document_chunks_fts` (Virtual FTS5 table)
  - `indexed_documents` (0 rows)
  - `memories` (0 rows)
  - `messages` (0 rows)
  - `reminders` (0 rows)
  - `schema_migrations` (4 rows — applied desktop migration versions 1..4)
  - `sessions` (1 row)
  - `user_tasks` (0 rows)
  - `working_memory` (0 rows)
- **Architectural Directive:**
  `database/oliver.db` has **completely separate semantics** from the central FastAPI backend. It manages local RAG document indexing, local task steps, and reminders for desktop offline operations. It must **NEVER** be merged with or migrated into the central PostgreSQL backend.

### 4.2 Backend Development SQLite Database (`backend/oliver_dev.db`)
- **File Size:** 94,208 bytes
- **Role:** Local SQLite database used by FastAPI during initial development when `DATABASE_URL` is unconfigured.
- **Tables (5):**
  - `users` (3 rows)
  - `conversations` (2 rows)
  - `messages` (3 rows)
  - `refresh_tokens` (6 rows)
  - `devices` (2 rows)
- **Alembic Version Table:** None exists. Schema was initialized dynamically via `Base.metadata.create_all(bind=engine)`.
- **Architectural Directive:**
  These rows are local development test data. PostgreSQL will be initialized with a clean, managed Alembic schema. Data migration/extraction from `oliver_dev.db` to PostgreSQL is intentionally isolated to **Stage 2.1A.7 (Data Migration & Reconciliation)**.

---

## 5. Alembic Configuration & Migration Identity Audit

### 5.1 Configuration Files
- **`backend/alembic.ini`:**
  - `script_location = backend/alembic`
  - `sqlalchemy.url`: Left intentionally blank (Line 15). Header explicitly mandates setting `MIGRATION_DATABASE_URL`.
- **`backend/alembic/env.py` (Verified in `8f1cc57`):**
  - `get_migration_url()` checks `os.environ["MIGRATION_DATABASE_URL"]` first, then parses `backend/.env` using `dotenv_values()`.
  - Fails closed with `RuntimeError` if missing.
  - Zero fallback to SQLite or runtime `settings.DATABASE_URL`.
  - Both `run_migrations_offline()` and `run_migrations_online()` bind to `get_migration_url()`.
- **`backend/alembic/versions/`:**
  - Currently contains only `.gitkeep`.
  - Zero migrations currently exist.

### 5.2 Application Startup Interaction (`backend/app/main.py:69-125`)
When `ENVIRONMENT=development` and `engine.dialect.name` is PostgreSQL:
1. `_verify_startup_schema()` executes:
   ```python
   script_dir = ScriptDirectory(str(script_location))
   heads = script_dir.get_heads()
   ```
2. If `not heads` → `RuntimeError("FATAL STARTUP BLOCKED: No Alembic migrations exist...")`.
3. If `len(heads) > 1` → `RuntimeError("FATAL STARTUP BLOCKED: Multiple Alembic migration heads...")`.
4. Queries live database `MigrationContext.get_current_heads()`.
5. Compares `current_rev == expected_head`. If mismatch or unmigrated → fail closed.

**Key Insight:** Simply authoring the initial migration file in `backend/alembic/versions/` satisfies check (1) and (2) at the script directory level. Check (4) and (5) enforce that the database is migrated before the application can accept HTTP requests.

---

## 6. PostgreSQL Role & Privilege Verification for Stage 2.1A.3

Inspection of `backend/scripts/init_postgres.sh` (committed in `8f1cc57`) confirms:

1. **Migration Role Identity:** Alembic connects as `oliver_migrator`.
2. **Schema Ownership:** `ALTER SCHEMA public OWNER TO oliver_migrator;` inside `oliver_db` guarantees `oliver_migrator` has full DDL rights to create tables, indexes, and constraints.
3. **Default Privileges:**
   ```sql
   ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
       GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;
   ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
       GRANT USAGE, SELECT ON SEQUENCES TO oliver_app_user;
   ```
   All 5 tables created by the migration will automatically inherit runtime DML grants for `oliver_app_user`.
4. **`alembic_version` Privilege Restriction (SEC-09):**
   When `oliver_migrator` executes the initial migration, Alembic creates `alembic_version`. Under the default privilege grant, `oliver_app_user` would receive write access to `alembic_version`.
   **Post-Migration Requirement:** Immediately following migration execution against a live database (Stage 2.1A.4/2.1A.5):
   ```sql
   REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE alembic_version FROM oliver_app_user;
   GRANT SELECT ON TABLE alembic_version TO oliver_app_user;
   ```
   This guarantees `oliver_app_user` maintains read-only access for `_verify_startup_schema()`.

---

## 7. Initial Migration Design (Deterministic Offline Authoring)

Because Docker Desktop is not yet installed on the host machine, live autogeneration (`alembic revision --autogenerate`) against PostgreSQL is not currently possible. However, the schema is 100% deterministic and statically defined in `Base.metadata`.

### 7.1 Proposed Revision File
- **Path:** `backend/alembic/versions/001_initial_schema.py`
- **Revision ID:** `001_initial_schema` (or standard 12-char alphanumeric hash, e.g., `a1b2c3d4e5f6`)
- **Down Revision:** `None`
- **Branch Labels:** `None`
- **Depends On:** `None`

### 7.2 Execution Order (`upgrade()`)
1. Create `users` table + indexes (`ix_users_id`, `ix_users_email` UNIQUE).
2. Create `conversations` table + indexes (`ix_conversations_id`, `ix_conversations_user_id`), FK -> `users.id` ON DELETE CASCADE.
3. Create `refresh_tokens` table + indexes (`ix_refresh_tokens_id`, `ix_refresh_tokens_user_id`, `ix_refresh_tokens_token_hash` UNIQUE), FK -> `users.id` ON DELETE CASCADE.
4. Create `devices` table + indexes (`ix_devices_id`, `ix_devices_user_id`), FK -> `users.id` ON DELETE CASCADE.
5. Create `messages` table + indexes (`ix_messages_id`, `ix_messages_conversation_id`, `ix_messages_user_id`), FK -> `conversations.id` ON DELETE CASCADE, FK -> `users.id` ON DELETE CASCADE.

### 7.3 Downgrade Order (`downgrade()`)
1. Drop `messages` (drops dependent FKs).
2. Drop `devices`.
3. Drop `refresh_tokens`.
4. Drop `conversations`.
5. Drop `users`.

---

## 8. Migration Execution Plan (Two-Phase Strategy)

To maintain absolute safety and respect infrastructure readiness, the migration workflow is divided into two distinct phases:

### Phase 1: Offline Authoring (Stage 2.1A.3 Scope)
- **Goal:** Author and validate the initial migration Python file offline.
- **Prerequisites:** Python 3.13, SQLAlchemy, Alembic (all installed and verified).
- **Actions:**
  1. Create `backend/alembic/versions/001_initial_schema.py` containing complete `upgrade()` and `downgrade()` methods matching `Base.metadata`.
  2. Verify syntax via `python -m py_compile backend/alembic/versions/001_initial_schema.py`.
  3. Verify Alembic offline head discovery: `python -c "from alembic.script import ScriptDirectory; print(ScriptDirectory('backend/alembic').get_heads())"`. Must return `('001_initial_schema',)`.
  4. Verify working tree and database safety.
- **Docker Required?** **NO.** Can be authorized and executed immediately.

### Phase 2: Live Application & Verification (Stage 2.1A.4/2.1A.5 Scope)
- **Goal:** Apply the authored migration against live PostgreSQL in Docker.
- **Prerequisites:** Docker Desktop installed, container running via `init_postgres.sh`, `psycopg` installed.
- **Actions:**
  1. Set `$env:MIGRATION_DATABASE_URL = "postgresql+psycopg://oliver_migrator:<pw>@localhost:5432/oliver_db"`.
  2. Execute `alembic upgrade head`.
  3. Execute post-migration grant script to restrict `alembic_version` to SELECT-only for `oliver_app_user`.
  4. Start FastAPI backend and verify `_verify_startup_schema()` succeeds against live revision.
  5. Run pytest Category A and Category B test suites.

---

## 9. Risk Register

| Risk ID | Title | Severity | Impact | Mitigation |
|---|---|---|---|---|
| **R-01** | Migration executed against SQLite development DB | **HIGH** | Corrupts `oliver_dev.db` with PostgreSQL DDL | `backend/alembic/env.py` fails closed if `MIGRATION_DATABASE_URL` is unset; never falls back to SQLite. |
| **R-02** | Migration executed using application credentials | **HIGH** | Fails with permission denied on schema public | `alembic/env.py` requires dedicated `MIGRATION_DATABASE_URL` (`oliver_migrator`). |
| **R-03** | Dual foreign keys in `messages` table dropped out of order | **MEDIUM** | Downgrade failure or locked constraints | Downgrade order strictly drops `messages` first before `conversations` or `users`. |
| **R-04** | `alembic_version` write privileges granted to runtime app | **MEDIUM** | Security boundary violation | Post-migration `REVOKE` statement strictly specified in Stage 2.1A.3 execution plan. |
| **R-05** | Accidental migration of desktop `database/oliver.db` | **CRITICAL** | Data loss or corruption of local RAG/task memory | Verified that `database/oliver.db` is an independent desktop database, excluded from central migration. |
| **R-06** | Autogenerate run without connected PostgreSQL instance | **MEDIUM** | Tool failure or empty migration generated | Use deterministic offline authoring based on `Base.metadata` rather than ungrounded CLI autogenerate. |

---

## 10. Blockers & Prerequisites

| Item | Prerequisite For | Status | Action Required |
|---|---|---|---|
| Stage 2.1A.3 (Offline Authoring) | Initial migration revision file | **READY** | User authorization to implement Stage 2.1A.3 |
| Docker Desktop installation | Stage 2.1A.4 (Container setup) | **BLOCKED (Host)** | User must install Docker Desktop before 2.1A.4 |
| `psycopg[binary]` installation | Stage 2.1A.5 (Live testing) | **BLOCKED (Host)** | User must install `psycopg` before 2.1A.5 |

---

## 11. Proposed Implementation Scope for Stage 2.1A.3

When authorized, Stage 2.1A.3 implementation is strictly limited to:

1. **Create:** `backend/alembic/versions/001_initial_schema.py`  
   Contains complete `upgrade()` and `downgrade()` definitions for all 5 tables and indexes matching `Base.metadata`.
2. **Validate:**  
   `python -m py_compile backend/alembic/versions/001_initial_schema.py`  
   `python -c "from alembic.script import ScriptDirectory; print(ScriptDirectory('backend/alembic').get_heads())"`
3. **Document:** `docs/OLIVER_3_PHASE_2_1A3_IMPLEMENTATION_REPORT.md`  
   Evidence report documenting revision ID, created schema objects, syntax checks, and offline head validation.

**Files NOT to touch in Stage 2.1A.3:**
- `backend/app/main.py` (already ready)
- `backend/app/core/*` (already ready)
- `backend/alembic/env.py` (already ready)
- Any database files (`.db`)
- Docker or shell scripts

---

## 12. Final Verdict & Recommendation

```
===========================================================================
STAGE 2.1A.3 READINESS VERDICT: READY WITH CONDITIONS

CONDITIONS:
1. Stage 2.1A.3 implementation must be restricted to deterministic OFFLINE
   authoring and syntax validation of the initial Alembic migration file.
2. Live migration execution (alembic upgrade head) is deferred to Stage
   2.1A.4/2.1A.5 when the Docker container is running.
3. database/oliver.db must remain untouched and permanently separate from
   the central PostgreSQL backend.
4. backend/oliver_dev.db data migration is deferred to Stage 2.1A.7.

STOPPING POINT:
Stage 2.1A.3 implementation is NOT yet authorized.
Awaiting explicit user authorization before creating the initial migration.
===========================================================================
```
