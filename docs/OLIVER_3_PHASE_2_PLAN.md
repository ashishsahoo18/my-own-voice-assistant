# OLIVER 3.0 — Master Plan: Phase 2 PostgreSQL & Shared Data

**Document:** `docs/OLIVER_3_PHASE_2_PLAN.md`  
**Status:** Approved for Planning Only (Phase 2.0 Refinement)  
**Strict Policy:** No code changes, no container execution, no database migrations, and no historical imports until explicit phase approval.

---

## 1. Selected Technology Choices

| Layer / Component | Technology | Rationale & Responsibility |
|---|---|---|
| **Database Engine** | PostgreSQL 16 (Alpine) | ACID compliant, MVCC multi-device concurrency, robust JSON handling, foreign key enforcement. |
| **Containerization** | Docker Compose | Isolated, reproducible container strictly bound to `127.0.0.1:5432` with persistent Docker named volume. |
| **Python Driver** | `psycopg` (psycopg 3) | Modern, fast, official PostgreSQL driver supporting binary parameters, native types, and connection pooling. |
| **ORM & Migrations** | SQLAlchemy 2.x + Alembic | Versioned, auditable database schema lifecycle with auto-generation and explicit downgrade capabilities. |
| **Application Backend**| FastAPI (Existing) | Asynchronous REST + WebSocket service mediating all client interactions, user auth, and AI orchestration. |
| **AI Inference** | Local Ollama (`llama3.2`) | Local workstation intelligence; strictly private, zero cloud fees, never exposed unauthenticated. |

---

## 2. Architecture Findings & Corrections

### A. SQLite Snapshot & Backup Safety
When creating a historical copy from the existing desktop database (`database/oliver.db`):
1. **Strict Read-Only Connection**:
   The source connection must be opened via SQLite URI syntax with `mode=ro`:
   ```python
   import os, sqlite3
   from pathlib import Path

   source_path = os.path.abspath("database/oliver.db")
   # Safe Windows path handling with spaces and drive letters
   file_url = Path(source_path).resolve().as_uri() + "?mode=ro"
   source_conn = sqlite3.connect(file_url, uri=True)
   ```
   When opened with `mode=ro`, the SQLite engine strictly prohibits writes and will fail immediately if any write operation is attempted.
2. **Safe Windows Path Handling**:
   Paths with spaces (e.g. `c:\Users\ASHISH\OneDrive\Desktop\Documents\my own voice assistant`) must use `Path.resolve().as_uri()` to ensure correct URI encoding (`%20`).
3. **WAL Mode & Active Connections**:
   `database/oliver.db` is configured in `wal` mode. When a database is in WAL mode, active transactions may reside in `oliver.db-wal` indexed by `oliver.db-shm`. Standard filesystem copies (`shutil.copyfile`) can produce torn or corrupt pages if copied while a process writes or checkpoints.
   Python's native `sqlite3.Connection.backup()` operates at the pager layer, pulling consistent committed pages across both the main database file and the WAL log.
4. **Clarification on `pages=0`**:
   Calling `backup(dst, pages=0)` or `backup(dst)` copies all pages until completion. **It does not mean the entire backup occurs in a single instantaneous atomic lock cycle.** If active writers touch the database while the backup progresses, SQLite detects the page version change and re-copies modified pages. For our quiescent desktop database, `backup()` produces an exact, transactionally consistent snapshot.
5. **Integrity Verification**:
   The copied snapshot in `scratch/oliver_snapshot.db` must be verified immediately after creation:
   ```sql
   PRAGMA integrity_check;
   SELECT COUNT(*) FROM sessions;
   SELECT COUNT(*) FROM messages;
   ```
6. **Zero Impact on Original Database**:
   The original `database/oliver.db` and its associated WAL/SHM files are never modified, checkpointed, renamed, or deleted.
7. **SQLite WAL and SHM Sidecar Protection**:
   - The desktop SQLite database uses Write-Ahead Logging (`-wal`) and Shared Memory (`-shm`) sidecar files.
   - Required `.gitignore` patterns to prevent committing transient WAL/SHM files:
     ```gitignore
     database/*.db-wal
     database/*.db-shm
     *.db-wal
     *.db-shm
     ```
   - *Repository Status Note:* Commit `be90df3` tracked `database/oliver.db-shm` and `database/oliver.db-wal`. Git will continue observing local access changes to `database/oliver.db-shm` until untracked in a future approved phase (`git rm --cached`).
   - *Strict Rule:* These files must never be manually edited, deleted, staged, or committed during development.

---

### B. PostgreSQL JSON Compatibility
- **Generic `sa.JSON` vs. PostgreSQL `JSONB`**:
  SQLAlchemy's generic `sa.JSON` maps to standard PostgreSQL `JSON` (which stores raw textual JSON and re-parses it on every access), **not** `JSONB`.
- **Targeted Application of `JSONB`**:
  PostgreSQL's binary `JSONB` supports GIN indexing, key existence testing (`?`), and containment queries (`@>`).
  For `User.preferences`, we will declare:
  ```python
  from sqlalchemy import JSON
  from sqlalchemy.dialects.postgresql import JSONB

  preferences: Mapped[dict] = mapped_column(
      JSON().with_variant(JSONB, "postgresql"),
      default=lambda: {"theme": "dark", "voice_enabled": True, "language": "en"}
  )
  ```
  This preserves SQLite development compatibility (using standard JSON/text) while unlocking native, indexed `JSONB` on PostgreSQL without altering Pydantic schema serialization or application behavior.

---

### C. UUID Identifier Compatibility
- **Decision**: Retain existing `String(36)` primary and foreign key identifiers for Phase 2.
- **Technical Rationale**:
  - `String(36)` maps to `VARCHAR(36)` in PostgreSQL and `TEXT` in SQLite.
  - Python's `str(uuid.uuid4())` generates standard 36-character hyphenated UUID strings that work identically across both database engines.
  - Converting to native PostgreSQL `UUID` (`sa.UUID(as_uuid=True)`) would introduce dialect-specific casting migrations (`USING id::uuid`), require custom TypeDecorators for SQLite test parity, and add zero user-facing functionality at this stage.
  - `String(36)` maintains 100% equivalence between SQLite dev and PostgreSQL production.

---

### D. Historical Import Idempotency & Provenance

#### 1. Rejection of `(conversation_id, created_at, role)` Uniqueness
Inspection of `database/oliver.db` proved that sequential user/assistant message pairs share **identical timestamps down to the second**:
- `ID=1`: `role='user'`, `created_at='2026-09-07T22:34:09'`, `content='open whatsapp'`
- `ID=2`: `role='assistant'`, `created_at='2026-09-07T22:34:09'`, `content='Opening WhatsApp Web.'`
- `ID=3`: `role='user'`, `created_at='2026-09-07T22:34:14'`, `content='open browser'`
- `ID=4`: `role='assistant'`, `created_at='2026-09-07T22:34:14'`, `content='I do not support opening browser yet.'`

Relying on `(conversation_id, created_at, role)` as a uniqueness constraint is unsafe. If rapid user inputs or retries occur in the same second, valid messages would be dropped or trigger collision errors. Title matching is similarly rejected because multiple conversations legitimately share identical titles (e.g., `"New Chat"`).

#### 2. Safe Deterministic Migration Identity Strategy
Inspection of the legacy schema confirms a stable integer primary key exists in SQLite:
`CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, ...)`

The migration identity will be derived deterministically from three immutable source attributes:
1. **Stable Source Database Identifier**: `source_db_id = "desktop_oliver_v2"` (assigned once and permanently retained in provenance columns).
2. **Legacy Session ID**: `legacy_session_id = session.session_id` (`"legacy_ayra_chat_1"`).
3. **Legacy Message ID**: `legacy_message_id = message.id` (Integers `1` through `8`).

#### 3. Deterministic Target Identifiers & Provenance Schema
- **UUIDv5 Canonical Input Strings**:
  - **Conversation Level**:
    `canonical_conv_str = f"oliver.legacy.{source_db_id}.{legacy_session_id}"`
    `target_conv_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, canonical_conv_str))`
  - **Message Level**:
    `canonical_msg_str = f"oliver.legacy.{source_db_id}.{legacy_session_id}.msg.{legacy_message_id}"`
    `target_msg_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, canonical_msg_str))`
- **Provenance Columns on Target Models**:
  - `Conversation` model:
    - `legacy_source_db: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)`
    - `legacy_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)`
    - Unique Constraint: `UniqueConstraint('user_id', 'legacy_source_db', 'legacy_session_id', name='uq_user_legacy_conv')`
  - `Message` model:
    - `legacy_source_db: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)`
    - `legacy_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)`
    - `legacy_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)`
    - Unique Constraint: `UniqueConstraint('legacy_source_db', 'legacy_session_id', 'legacy_message_id', name='uq_source_session_msg')`
- **Compatibility with Ordinary New Messages**:
  `legacy_source_db`, `legacy_session_id`, and `legacy_message_id` are strictly `nullable=True`. For ordinary new messages created in OLIVER 3.0 via `POST /api/chat`, these columns default to `NULL`. In standard SQL and PostgreSQL, unique constraints ignore rows with `NULL` in nullable columns (or use a partial unique index `WHERE legacy_message_id IS NOT NULL`), ensuring 100% compatibility with ordinary messaging.
- **Cross-Database Isolation**:
  If future migrations import data from another device or backup (e.g. `source_db_id = "phone_backup_2026"`), the composite key `(source_db_id, legacy_session_id, legacy_message_id)` guarantees uniqueness across distinct source databases even if both source databases used message ID `1`.

#### 4. Safe Ordering & Repeatable Execution
- **Ordering**: The migration reads messages using `ORDER BY id ASC`. Messages are inserted sequentially preserving exact historical order and original `created_at` timestamps.
- **Idempotent Re-execution**: Before inserting any message, the migration queries PostgreSQL for existing records matching `(legacy_source_db, legacy_session_id, legacy_message_id)`. Any existing record is skipped (`SKIPPED_EXISTING`), guaranteeing that running the migration multiple times produces zero duplicate messages without relying on timestamps, titles, or message text.
- **Repeatable Preview**: A mandatory `--preview` mode outputs a dry-run table (IDs, roles, timestamps, content preview, collision status) without executing write transactions.

---

### E. Backup, Rollback, and Fallback Strategy

#### 1. PostgreSQL Backup & Restore
- Before running any migration or import on existing PostgreSQL data:
  ```powershell
  pg_dump -h 127.0.0.1 -p 5432 -U oliver_user -d oliver_db -F c -f database/backups/pg_pre_migration.dump
  ```
- **Risks of `pg_restore --clean`**:
  `pg_restore --clean` issues `DROP TABLE` before recreating tables. If the restore fails halfway (due to missing extensions, permissions, or corrupt archive bytes), the original tables are already destroyed!
  **Safe Procedure:** Test the restore first against a disposable database (`oliver_test_restore`). In production, restore into a fresh database and swap connection strings once verification succeeds.
- **Never use `alembic downgrade base` as a production rollback**:
  `downgrade base` drops all tables and wipes all user data. It is strictly for clean-slate test teardown.

#### 2. Backend SQLite Fallback
- The backend's local offline database is `backend/oliver_dev.db`.
- If PostgreSQL or Docker is unavailable, set `DATABASE_URL="sqlite:///./backend/oliver_dev.db"` in `backend/.env` and restart Uvicorn.
- **Crucial Boundary Note**: Switching the backend back to `backend/oliver_dev.db` does **NOT** synchronize data from PostgreSQL, nor does it reverse transactions committed to PostgreSQL. It merely redirects application queries back to the independent local development store.
- **The desktop SQLite database (`database/oliver.db`) is NEVER used as a backend database.**

#### 3. Interrupted Historical Import Recovery
- Historical data import runs inside a single atomic transaction (`with db.begin():`). If an error occurs on any message, the entire transaction rolls back.
- If an import must be reverted post-commit, a dedicated CLI command `migrate_sqlite --revert --legacy-session <session_id>` removes the imported conversation and cascading messages without touching newly created conversations.

---

### F. Git Commit Metadata & Workstation Clock Verification

#### 1. Git Commit Metadata Inspection
Command:
```powershell
git log -1 --format="commit: %H%nauthor_name: %an%nauthor_email: %ae%nauthor_date_raw: %at%nauthor_date_iso: %ai%ncommitter_date_raw: %ct%ncommitter_date_iso: %ci" c33e4461334f55fb65e8638ff8f7327881cdabba
```
Output:
```text
commit: c33e4461334f55fb65e8638ff8f7327881cdabba
author_name: ashishsahoo18
author_email: sahooashish673@gmail.com
author_date_raw: 1794093618
author_date_iso: 2026-11-07 18:20:18 -0500
committer_date_raw: 1794093618
committer_date_iso: 2026-11-07 18:20:18 -0500
```
- **Author Timestamp (Raw Epoch):** `1794093618` (`2026-11-07 18:20:18`)
- **Author Timezone Offset:** `-0500` (EST)
- **Committer Timestamp (Raw Epoch):** `1794093618` (`2026-11-07 18:20:18`)
- **Committer Timezone Offset:** `-0500` (EST)

#### 2. Workstation Clock & Timezone Inspection
Commands:
```powershell
Get-Date -Format o
Get-TimeZone
(Get-Date).ToUniversalTime().ToString('o')
```
Exact Outputs:
```text
Local Time (ISO 8601): 2026-11-07T18:50:20.8910520-05:00

Timezone Details:
Id                         : US Eastern Standard Time
DisplayName                : (UTC-05:00) Indiana (East)
StandardName               : US Eastern Standard Time
DaylightName               : US Eastern Standard Time
BaseUtcOffset              : -05:00:00
SupportsDaylightSavingTime : False

UTC Time (ISO 8601):    2026-11-07T23:50:20.9321490Z
```

#### 3. Evaluation of Workstation vs. Review-Time Discrepancy
- The workstation system clock consistently reports evening time (`18:50:20 -05:00`, UTC `23:50:20Z`), and all local Git commits (`c33e446` at `18:20:18`, `b95c45d` at `18:46:22`, `c43ed9b` at `18:46:25`) align with this workstation clock.
- The external review-time reference indicates morning time (approximately `2026-11-07T08:08:00-05:00`), diverging by approximately 10 hours and 42 minutes.
- **Finding:** The workstation clock is **inconsistent** with the external review-time reference. Because this divergence cannot be independently reconciled using repository or system artifacts alone, it is formally recorded as **unresolved**. No changes have been made to the system clock or Git history.

---

## 3. Confirmed Target Architecture

```
┌──────────────────────────────────────┐
│  Windows CustomTkinter Desktop HUD   │
│  (Existing OLIVER 2.0 Client)        │
└──────────────────┬───────────────────┘
                   │
                   │ HTTPS / WSS (Future)
                   ▼
┌──────────────────────────────────────┐       Local HTTP (127.0.0.1:11434)
│        FastAPI Central Backend       ├──────────────────────────────────► ┌────────────────────────┐
│   Authentication, Orchestration,     │                                    │  Ollama Local LLM      │
│   Rate Limiting, User Isolation      │                                    │  (llama3.2:latest)     │
└──────────────────┬───────────────────┘                                    └────────────────────────┘
                   │                                                                   ▲
                   │ Authenticated Connection                                          │ Strictly Private:
                   ▼                                                                   │ Mobile NEVER talks
┌──────────────────────────────────────┐                                               │ directly to Ollama
│       PostgreSQL 16 Database         │                                               │
│  (Docker Compose - 127.0.0.1:5432)   │                                               │
└──────────────────────────────────────┘                                               │
                   ▲                                                                   │
                   │ HTTPS / WSS                                                       │
┌──────────────────┴───────────────────┐                                               │
│         Flutter Mobile App           ├───────────────────────────────────────────────┘
│  (Android / iOS - Authenticated)     │
└──────────────────────────────────────┘
```

### Architectural Principles:
1. **Shared Database**: PostgreSQL 16 is the planned shared database across desktop and mobile.
2. **Preserved Desktop SQLite**: `database/oliver.db` remains the offline desktop store, completely isolated from network services.
3. **Separate Backend SQLite**: `backend/oliver_dev.db` remains the offline backend development database.
4. **Ollama Security**: Mobile clients **never** connect directly to Ollama on port 11434. All inference requests route through authenticated backend endpoints.

---

## 4. Database Preservation Rules

1. **Rule 1 (Zero Desktop Touches)**: Never write, checkpoint, modify, or delete `database/oliver.db` or its WAL/SHM files.
2. **Rule 2 (Sidecar Protection)**: Preserve `database/oliver.db-wal` and `database/oliver.db-shm`. Do not delete, stage, commit, or manually edit them. Include `*.db-wal` and `*.db-shm` in `.gitignore`.
3. **Rule 3 (Snapshot First)**: Historical migrations must operate exclusively on an independent copy created via `sqlite3.Connection.backup()`.
4. **Rule 4 (Backend Dev Isolation)**: `backend/oliver_dev.db` is an independent test/dev file. It must not be overwritten or treated as production data.
5. **Rule 5 (No Blind Downgrades)**: Production rollbacks must use point-in-time database dumps, never `alembic downgrade base`.

---

## 5. Phased Implementation Sequence

```mermaid
flowchart TD
    P20["Phase 2.0: Planning Review (CURRENT)"] --> P21["Phase 2.1: Docker & PostgreSQL Infrastructure"]
    P21 --> P22["Phase 2.2: Alembic Initial Migration"]
    P22 --> P23["Phase 2.3: PostgreSQL Integration & Testing"]
    P23 --> P24["Phase 2.4: Read-Only Historical Migration Preview"]
    P24 --> P25["Phase 2.5: Historical Data Import (Separate Approval)"]
```

### Phase 2.1: Docker Compose & PostgreSQL Infrastructure
- **Objective**: Stand up PostgreSQL 16 Alpine container locally.
- **Files Affected**: `docker-compose.yml`, `backend/requirements.txt` (add `psycopg[binary]`), `backend/.env.example`.
- **Dependencies**: Docker Desktop running on Windows workstation.
- **Risks**: Port 5432 already occupied; container volume permissions.
- **Verification**: `docker compose up -d`, `pg_isready -h 127.0.0.1 -p 5432`.
- **Exit Criteria**: PostgreSQL container healthy and reachable on `127.0.0.1:5432`.

### Phase 2.2: Alembic Initial Migration
- **Objective**: Generate and apply the initial versioned schema to PostgreSQL.
- **Files Affected**: `backend/alembic/versions/<revision>_initial_oliver_schema.py`, `backend/app/main.py` (gate `create_all()` to dev SQLite).
- **Dependencies**: Phase 2.1 complete.
- **Risks**: Dialect incompatibilities during revision generation.
- **Verification**: `alembic upgrade head`, inspect `alembic_version` table in PostgreSQL.
- **Exit Criteria**: All 5 tables (`users`, `refresh_tokens`, `conversations`, `messages`, `devices`) cleanly created in PostgreSQL with proper constraints and indexes.

### Phase 2.3: PostgreSQL Integration & Testing
- **Objective**: Validate backend FastAPI operation against PostgreSQL.
- **Files Affected**: `backend/.env` (`DATABASE_URL` pointed to PostgreSQL), `backend/tests/`.
- **Dependencies**: Phase 2.2 complete.
- **Risks**: Transaction or timezone issues under PostgreSQL driver.
- **Verification**:
  - `pytest backend/tests/ -v` passing 100% against PostgreSQL.
  - Live HTTP probe (`scratch/live_probe.py`) against PostgreSQL backend.
- **Exit Criteria**: All 14 tests pass, all 13 live endpoints return HTTP 200/201 with verified latencies.

### Phase 2.4: Read-Only Historical Migration Preview
- **Objective**: Safe snapshot creation and dry-run preview of historical SQLite data.
- **Files Affected**: `backend/scripts/migrate_sqlite.py`, `scratch/oliver_snapshot.db`.
- **Dependencies**: Phase 2.3 complete, target user account registered.
- **Risks**: None (strictly read-only snapshot, zero writes to PostgreSQL).
- **Verification**: CLI outputs preview table of 1 session and 8 messages with proposed UUID mappings.
- **Exit Criteria**: Accurate preview output approved by user.

### Phase 2.5: Historical Data Import (Requires Separate Approval)
- **Objective**: Execute atomic import into PostgreSQL.
- **Files Affected**: PostgreSQL `conversations` and `messages` tables.
- **Dependencies**: Phase 2.4 approved, PostgreSQL pre-import dump completed.
- **Risks**: Duplicate import if interrupted.
- **Verification**:
  - Database verification: 1 conversation and 8 messages queryable in PostgreSQL for owner account.
  - Original `database/oliver.db` checksum verified 100% unchanged.
- **Exit Criteria**: Historical data queryable via `GET /api/conversations/{id}/messages`.

---

## 6. Checklist of Decisions Requiring User Confirmation Before Phase 2.1

- [ ] Confirm Docker Desktop is installed and available to run `docker compose`.
- [ ] Confirm PostgreSQL container will bind strictly to `127.0.0.1:5432`.
- [ ] Confirm use of `psycopg` (psycopg 3) as the Python database driver.
- [ ] Confirm target owner email for historical data import (when Phase 2.4/2.5 is reached).
