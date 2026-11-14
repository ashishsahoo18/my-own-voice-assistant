# OLIVER 3.0 — Phase 2.1
## PostgreSQL + Docker Architecture — Corrected Planning & Final Readiness Review

**Document Version:** 2.0 (Final Corrected Readiness Review)  
**Supersedes:** `docs/OLIVER_3_PHASE_2_1_POSTGRESQL_DOCKER_PLANNING_REPORT.md` (v1.0)  
**Milestone:** Phase 2.1 — Central Backend PostgreSQL Migration  
**Audit Mode:** STRICTLY READ-ONLY PLANNING & ARCHITECTURE REVIEW  
**Date:** 2026-11-14  
**Project Root:** `C:\Users\ASHISH\OneDrive\Desktop\Documents\my own voice assistant`  
**Git HEAD:** `8e7ceac` ("New added.") on branch `main`  
**Pre-existing Working Tree Deletions:** `database/oliver.db-shm`, `database/oliver.db-wal` (tracked WAL artifacts, preserved untouched)  
**Untracked Reports Present:**  
- `docs/OLIVER_3_PHASE_2A1_3_STAGE_2E_FINAL_READINESS_AUDIT.md`  
- `docs/OLIVER_3_PHASE_2_1_POSTGRESQL_DOCKER_PLANNING_REPORT.md`  
**Final Verdict:** **NOT READY** (Blocked by two critical missing infrastructure dependencies: Docker Desktop not installed and `psycopg` driver not present in environment)

---

## 1. Executive Summary

This document provides a strictly read-only, evidence-based correction and final readiness review for migrating the OLIVER 3.0 central backend from SQLite (`backend/oliver_dev.db`) to PostgreSQL deployed via Docker.

The review of the initial Phase 2.1 planning report (`OLIVER_3_PHASE_2_1_POSTGRESQL_DOCKER_PLANNING_REPORT.md`) revealed critical architectural, security, lifecycle, and testing deficiencies that required thorough remediation:

1. **PostgreSQL Superuser Privilege Leak:** The initial plan assigned `POSTGRES_USER: oliver_user` directly in Docker Compose, which by PostgreSQL entrypoint semantics grants cluster-wide `SUPERUSER` privileges to the application runtime.
2. **Configuration & Secrets Ambiguity:** No clear separation was defined between root `.env`, `backend/.env`, and Docker Compose variable interpolation. In this repository, `backend/.env` does not exist; configuration is loaded with fallback to root `.env`.
3. **Schema Management Conflicts:** The application lifespan (`backend/app/main.py`) executes `Base.metadata.create_all(bind=engine)` unconditionally, which bypasses Alembic, prevents `alembic_version` tracking, and risks DDL collisions upon subsequent migrations.
4. **Superficial Rollback Strategy:** Reverting `DATABASE_URL` to SQLite was proposed as an instant rollback, completely failing to address post-cutover data loss, split-brain states, or data reconciliation.
5. **Inconsistent Implementation Stages:** Sections 8 and 11 contained mismatched stage sequences (8 stages vs. 7 stages) with conflicting scopes and numbering.
6. **Missing Container Health Checks:** Acceptance criteria mandated a "healthy" container status, yet the proposed Docker Compose configuration omitted a `healthcheck` block entirely.
7. **Flawed Testing Assumptions:** The existing 195-test Stage 2E baseline (desktop UI, Vosk STT, URL trust, telemetry) was conflated with backend PostgreSQL verification, even though those tests never connect to FastAPI or PostgreSQL.

This corrected plan establishes an authoritative, security-hardened architecture, a unified 7-stage implementation sequence (Stages 2.1A through 2.1G), a 10-point backup and recovery framework, and four independent testing categories.

**Readiness Conclusion:** The project architecture is fundamentally sound and ready for migration once prerequisites are met, but the current readiness status must be formally classified as **NOT READY** because Docker Desktop is absent from the host system and the `psycopg` driver is missing. Implementation must NOT begin until these prerequisites are satisfied and explicit user authorization is granted.

---

## 2. Original Report Assessment

The initial planning report (`OLIVER_3_PHASE_2_1_POSTGRESQL_DOCKER_PLANNING_REPORT.md`) successfully identified the modern SQLAlchemy 2.x ORM structure and the independence of the desktop database (`database/oliver.db`). However, a critical audit revealed major planning defects:

| Assessment Area | Original Plan Defect | Corrective Action in This Review |
|---|---|---|
| **User Privileges** | Used single `oliver_user` via `POSTGRES_USER`, making the application runtime a PostgreSQL superuser. | Designed a three-tier role architecture (`postgres` admin, `oliver_migrator` DDL owner, `oliver_app` DML-only runtime) with least privilege. |
| **Secrets & .env Files** | Assumed `backend/.env` was primary without inspecting existence; ignored Compose reading root `.env`. | Documented exact path resolution, verified `.gitignore` coverage, and unified secret passing without Git leakage. |
| **Schema Ownership** | Permitted `create_all()` to remain in `main.py` lifespan, undermining Alembic authority. | Mandated explicit dialect gating: `create_all()` strictly restricted to SQLite dev mode; disabled for PostgreSQL. |
| **Rollback & Data Loss** | Treated reverting `DATABASE_URL` as a safe rollback, ignoring post-cutover writes. | Formulated a 10-point backup, recovery, and delta-reconciliation plan to prevent split-brain data loss. |
| **Stage Sequencing** | Section 8 had 8 stages (A–H); Section 11 had 7 stages (A–G) with mismatched scopes and names. | Reconciled all planning into ONE authoritative sequence (Stages 2.1A–2.1G) used consistently throughout. |
| **Health Check** | Stated container would show "healthy" with zero `healthcheck` definition in Compose YAML. | Defined explicit `pg_isready` health check with intervals, retries, start period, and backend `depends_on`. |
| **Testing Strategy** | Claimed 195 desktop tests verified PostgreSQL backend operation. | Separated verification into 4 distinct categories: SQLite unit, PostgreSQL integration, Desktop regression, and E2E. |

---

## 3. Git and Project Baseline

### 3.1 Preflight Repository Inspection

A strictly read-only inspection of the repository was conducted:

- **Current Working Directory:** `C:\Users\ASHISH\OneDrive\Desktop\Documents\my own voice assistant`
- **Active Git Branch:** `main`
- **Current HEAD Commit:** `8e7ceac` (*"New added."*)
- **Working Tree Status (`git status --short`):**
  ```
   D database/oliver.db-shm
   D database/oliver.db-wal
  ?? docs/OLIVER_3_PHASE_2A1_3_STAGE_2E_FINAL_READINESS_AUDIT.md
  ?? docs/OLIVER_3_PHASE_2_1_POSTGRESQL_DOCKER_PLANNING_REPORT.md
  ```
- **Tracked Deletions:** `database/oliver.db-shm` and `database/oliver.db-wal` are tracked in the Git index (committed in earlier milestones) but deleted from disk by the SQLite runtime or test runner. Per mandatory constraints, these files are preserved as-is and will NOT be restored, staged, or removed.
- **Untracked Reports:** The Stage 2E audit and initial Phase 2.1 planning reports remain untouched.

### 3.2 Environment & Tooling Verification

| Component | Target Version | Verified State | Status | Evidence |
|---|---|---|---|---|
| **Operating System** | Windows 10 / 11 64-bit | Windows-11-10.0.26300-SP0 AMD64 | ✅ Confirmed | `platform.platform()` |
| **Python Runtime** | 3.13.5 64-bit | Python 3.13.5 (v3.13.5:6cb20a2) | ✅ Confirmed | `sys.version` |
| **Docker Engine** | 24+ / Compose v2 | `docker : The term 'docker' is not recognized` | ❌ **NOT INSTALLED** | CLI error code 1 |
| **Docker Compose** | v2.20+ | `docker compose : Not recognized` | ❌ **NOT INSTALLED** | CLI error code 1 |
| **PostgreSQL Driver** | `psycopg[binary]>=3.2.0` | Absent from backend and root `requirements.txt` | ❌ **NOT INSTALLED** | File inspection |
| **SQLAlchemy** | 2.0.30+ | `sqlalchemy>=2.0.30` in `backend/requirements.txt` | ✅ Configured | `backend/requirements.txt` |
| **Alembic** | 1.13.0+ | `alembic>=1.13.0` in `backend/requirements.txt` | ✅ Configured | `backend/requirements.txt` |

---

## 4. Current Architecture Analysis

### 4.1 Two Independent Database Domains

The project maintains two completely separated database architectures with zero shared schema or runtime dependencies:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        OLIVER 3.0 Architecture                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          ▼                                                   ▼
┌───────────────────────────────────┐       ┌───────────────────────────────────┐
│     Desktop Application Domain    │       │     Central Backend Domain        │
│  (CustomTkinter, Voice, Browser)  │       │      (FastAPI, Ollama Sync)       │
├───────────────────────────────────┤       ├───────────────────────────────────┤
│ Database: database/oliver.db      │       │ Database: backend/oliver_dev.db   │
│ Engine: Native SQLite3 (FTS5)     │       │ Engine: SQLAlchemy 2.x            │
│ Scope: Local offline persistence  │       │ Scope: Shared multi-device data   │
│ Migration Target: PERMANENT SQLITE│       │ Migration Target: POSTGRESQL / DOCKER
└───────────────────────────────────┘       └───────────────────────────────────┘
```

### 4.2 Backend Database (`backend/oliver_dev.db`)

- **Current State:** Single-file SQLite database located in `backend/`.
- **ORM Technology:** SQLAlchemy 2.x modern Declarative Base (`Mapped`, `mapped_column`).
- **Entity Inventory (5 Tables):**
  1. `users`: UUID PK, unique email, bcrypt hash, full name, JSON preferences text, active boolean, timestamps.
  2. `refresh_tokens`: UUID PK, FK to `users.id` (CASCADE), SHA-256 token hash, expiry, revoked flag.
  3. `conversations`: UUID PK, FK to `users.id` (CASCADE), title, timestamps.
  4. `messages`: UUID PK, FK to `conversations.id` (CASCADE), FK to `users.id` (CASCADE), role, content text, latency float, timestamp.
  5. `devices`: UUID PK, FK to `users.id` (CASCADE), device name, type, platform, client version, timestamps.
- **Current Live Rows (Development Data):** 3 users, 6 refresh tokens, 2 conversations, 3 messages, 2 devices.
- **Alembic Status:** Scaffold present in `backend/alembic/`, `backend/alembic.ini` present, but `backend/alembic/versions/` contains **only `.gitkeep`**. Zero migrations have been generated or executed.

### 4.3 Desktop Database (`database/oliver.db`)

- **Tables:** 20+ tables including `sessions`, `messages`, `memories`, `working_memory`, `notes`, `reminders`, `user_tasks`, `agent_tasks`, `agent_task_steps`, `indexed_documents`, and `document_chunks`.
- **SQLite-Specific Features:** Utilizes SQLite's native `fts5` virtual table extension (`document_chunks_fts`, `notes_fts`) with unicode61/porter tokenizers.
- **Migration Architecture:** Uses an independent SQLite migration tracker (`schema_migrations` table) and custom migration scripts.
- **Coexistence Mandate:** Must remain 100% SQLite. Migrating this database to PostgreSQL is strictly prohibited as it would destroy offline-first desktop voice capabilities and invalidate the FTS5 RAG subsystem.

---

## 5. Seven Mandatory Findings and Technical Resolutions

### Finding 1 — PostgreSQL User Privileges & Role Architecture

#### 1.1 The Vulnerability in the Original Proposal
The original proposal specified `POSTGRES_USER: oliver_user` in the Docker Compose environment. In the official PostgreSQL Docker image, the user defined by `POSTGRES_USER` is automatically created with **`SUPERUSER`** privileges. Consequently, the FastAPI application runtime would connect with unrestricted administrative rights, violating the principle of least privilege and allowing potential SQL injection or application vulnerabilities to execute cluster-level administrative operations.

#### 1.2 The Three-Tier Role Solution
To secure the PostgreSQL deployment, three distinct roles must be established:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PostgreSQL Role Hierarchy                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  postgres (Admin)│      │ oliver_migrator  │      │   oliver_app     │
├──────────────────┤      ├──────────────────┤      ├──────────────────┤
│ - Cluster admin  │      │ - DDL Owner      │      │ - DML Runtime    │
│ - Superuser      │      │ - Non-superuser  │      │ - Non-superuser  │
│ - Container init │      │ - Schema creator │      │ - SELECT/INSERT  │
│ - Disaster recov │      │ - Used by Alembic│      │ - UPDATE/DELETE  │
│ - No app traffic │      │ - No data access │      │ - NO DDL RIGHTS  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

1. **Bootstrap / Administrative Account (`postgres`):**
   - Configured via `POSTGRES_USER=postgres` and `POSTGRES_PASSWORD=${POSTGRES_ADMIN_PASSWORD}`.
   - Retains cluster-wide `SUPERUSER` privileges.
   - Used solely by the container entrypoint to execute initialization scripts, take physical backups (`pg_dump`), and perform cluster recovery. Never accessed by application runtime code.
2. **Migration Account (`oliver_migrator`):**
   - Created during database initialization.
   - Granted `CREATE` and `USAGE` on schema `public` in database `oliver`.
   - Owns the database schema and tables.
   - Possesses DDL privileges (CREATE, ALTER, DROP, INDEX), allowing Alembic to execute schema evolutions.
   - Does NOT have cluster superuser privileges; cannot access filesystem or create other databases.
3. **Application Runtime Account (`oliver_app`):**
   - Created during database initialization with `LOGIN` and a dedicated password `${POSTGRES_APP_PASSWORD}`.
   - Granted `CONNECT` on database `oliver` and `USAGE` on schema `public`.
   - Granted `SELECT, INSERT, UPDATE, DELETE` on all existing tables and sequences.
   - Configured with `ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app;` and `GRANT USAGE, SELECT ON SEQUENCES TO oliver_app;`.
   - **Zero DDL rights:** Cannot execute `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, or `TRUNCATE`.

#### 1.3 Volume Initialization Lifecycle Nuance
- **Fresh Named Volume (`oliver_postgres_data`):** The PostgreSQL entrypoint detects an empty data directory, initializes `initdb`, creates the `postgres` superuser, and executes all `.sql` and `.sh` scripts mounted in `/docker-entrypoint-initdb.d/` in alphabetical order. This is where roles and initial privileges are established.
- **Existing Named Volume:** When the container restarts against an existing volume, `initdb` is **skipped completely**. PostgreSQL logs `PostgreSQL Database directory appears to contain a database; Skipping initialization` and ignores `/docker-entrypoint-initdb.d/`.
- **Operational Requirement:** Any future role modifications, password rotations, or privilege adjustments on an existing volume must be executed via explicit administrative migration scripts run by the `postgres` administrator, never assumed to happen via container restart.

---

### Finding 2 — Docker Compose Secrets and Environment Files

#### 2.1 Verified State of Repository Environment Files
Direct inspection revealed:
- `backend/.env` **does not exist** (verified via `Test-Path`).
- Root `.env` **exists** at `C:\Users\ASHISH\OneDrive\Desktop\Documents\my own voice assistant\.env`.
- Root `.gitignore` contains `.env` and `.env.*` (ignoring `.env` anywhere in the repository, verified via `git check-ignore`).
- `backend/app/core/config.py` loads configuration via:
  ```python
  model_config = SettingsConfigDict(
      env_file=(str(BACKEND_DIR / ".env"), str(BACKEND_DIR.parent / ".env")),
      env_file_encoding="utf-8",
      extra="ignore",
  )
  ```
  FastAPI attempts to read `backend/.env` first; when absent, it seamlessly falls back to the root `.env`.

#### 2.2 Docker Compose Variable Interpolation Mechanics
When running `docker compose up` from the project root:
- Docker Compose automatically searches for `.env` in the current working directory (the project root).
- Variables defined in root `.env` (such as `POSTGRES_ADMIN_PASSWORD` and `POSTGRES_APP_PASSWORD`) are interpolated into `docker-compose.yml`.
- If an engineer created `backend/.env` containing PostgreSQL passwords without placing them in the root `.env`, Docker Compose would fail to interpolate the variables and substitute blank values or raise warnings.

#### 2.3 Single Source of Truth Configuration Model
To eliminate configuration fragmentation:
1. **Authoritative Environment File:** The root `.env` is designated as the single local environment file for developer orchestration on Windows.
2. **Credential Routing:**
   ```
   [Root .env]
       ├── POSTGRES_ADMIN_PASSWORD ──► Docker Compose (postgres container)
       ├── POSTGRES_APP_PASSWORD   ──► Docker Compose (init script via env)
       └── DATABASE_URL            ──► FastAPI Settings (via fallback in config.py)
   ```
3. **Application URL Format:**
   `DATABASE_URL=postgresql+psycopg://oliver_app:${POSTGRES_APP_PASSWORD}@127.0.0.1:5432/oliver`
4. **Missing Credential Detection:**
   In `backend/app/core/config.py`, add a Pydantic `@field_validator("DATABASE_URL")` that rejects connections containing placeholder strings (`CHANGE_ME`, `password`, or empty credentials), aborting FastAPI startup immediately with an actionable error.
5. **Secret Redaction:**
   - Both root and nested `.env` files are confirmed excluded by `.gitignore`.
   - FastAPI logging middleware (`backend/app/main.py`) logs HTTP requests and latency but never dumps request bodies containing passwords (`/api/auth/login`, `/api/auth/register`).
   - SQLAlchemy connection URLs must never be printed to stdout. Ensure `echo=False` remains set on the production engine.

---

### Finding 3 — Alembic as the Authoritative Schema Manager

#### 3.1 The Danger of Unrestricted `create_all()`
In `backend/app/main.py` lines 32–34:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database schema for OLIVER 3.0...")
    # Create tables if not existing (dev SQLite mode)
    Base.metadata.create_all(bind=engine)
    ...
```
If `Base.metadata.create_all(bind=engine)` runs against a PostgreSQL database:
- SQLAlchemy issues raw DDL (`CREATE TABLE ...`) directly to the database.
- The `alembic_version` metadata tracking table is **never created**.
- When an engineer subsequently attempts to execute `alembic upgrade head`, Alembic fails with fatal errors (`Relation "users" already exists`).
- Furthermore, because the runtime account `oliver_app` will have DDL permissions stripped (Finding 1), calling `create_all()` at startup will crash with `psycopg.errors.InsufficientPrivilege: permission denied for schema public`.

#### 3.2 Formal Policy for Schema Management Across Modes
The schema management strategy is defined as follows:

| Operating Environment | Active Database | Schema Manager | `create_all()` Permitted? |
|---|---|---|---|
| **Production / Staging** | PostgreSQL | Alembic (`alembic upgrade head`) | ❌ **STRICTLY PROHIBITED** |
| **Local PostgreSQL Dev** | PostgreSQL (Docker) | Alembic (`alembic upgrade head`) | ❌ **STRICTLY PROHIBITED** |
| **Local SQLite Dev** | `oliver_dev.db` | Gated fallback (`create_all`) | ⚠️ Permitted with warning log |
| **Unit Testing (Category A)** | SQLite `:memory:` | Test fixture (`conftest.py`) | ✅ Permitted for isolation |
| **Integration Testing (Category B)** | PostgreSQL `oliver_test` | Alembic (`alembic upgrade head`) | ❌ Must test real migrations |

#### 3.3 Lifespan Gating Implementation
In Stage 2.1E, modify `backend/app/main.py` to strictly gate schema initialization:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.DATABASE_URL.startswith("sqlite"):
        logger.warning("Running in SQLite dev mode: initializing schema via Base.metadata.create_all()")
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("Running in PostgreSQL mode: schema management is delegated exclusively to Alembic.")
        # Optional: verify alembic_version table exists without issuing DDL
    yield
```
**Acceptance Criterion:** A PostgreSQL deployment is invalid unless the `alembic_version` table exists and contains the head revision identifier.

---

### Finding 4 — Comprehensive Backup, Rollback, and Recovery Framework

#### 4.1 The Fallacy of the Simple SQLite Rollback
The initial report stated that rollback consisted of setting `DATABASE_URL` back to SQLite in `.env`. This assumption is catastrophic in a live environment:
- Once the backend is cut over to PostgreSQL, all new user registrations, chat conversations, messages, refresh tokens, and device records are written to PostgreSQL.
- If an issue occurs 48 hours post-cutover and `DATABASE_URL` is flipped back to `oliver_dev.db`, all data written to PostgreSQL during those 48 hours is completely invisible to SQLite.
- The application enters a split-brain state: users cannot log in (their accounts only exist in PostgreSQL), chat histories are broken, and data is effectively lost.

#### 4.2 The 10-Point Backup and Recovery Strategy

```
┌────────────────────────────────────────────────────────────────────────┐
│                   10-Point Disaster Recovery Strategy                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
[Pre-Cutover Protection]     [PostgreSQL Operations]      [Disaster Rollback]
1. SQLite Cold Backup        3. Pre-Migration pg_dump    7. Application Rollback
2. SHA-256 Verification      4. pg_restore Dry-Run       8. Post-Cutover Delta Sync
                             5. Migration Failure Recov  9. Named Volume Recovery
                             6. Container Startup Recov 10. Acceptance Validation
```

1. **Pre-Cutover SQLite Cold Backup:**
   Before any cutover or data migration, stop the backend and take a byte-for-byte copy:
   `copy backend\oliver_dev.db backups\oliver_dev_pre_cutover_<timestamp>.db`.
2. **Backup Integrity Verification:**
   Execute `sqlite3 backups/oliver_dev_pre_cutover_<timestamp>.db "PRAGMA integrity_check;"` and compute a SHA-256 checksum stored in `backups/checksums.txt`.
3. **Pre-Migration PostgreSQL Backup:**
   Before running any new Alembic migration in PostgreSQL, execute a binary dump:
   `docker exec oliver_postgres pg_dump -U postgres -F c -b -v -f /var/lib/postgresql/data/pre_migration.dump oliver`.
4. **PostgreSQL Restore Verification:**
   Verify dump restorability by running `pg_restore --dry-run` or restoring to a disposable test database (`oliver_verify`).
5. **Failed Migration Recovery:**
   If `alembic upgrade head` fails:
   - Do NOT run `alembic downgrade -1` blindly if the migration failed halfway through non-transactional DDL.
   - If the database was left in an indeterminate state, drop the schema and restore from `pre_migration.dump`:
     `docker exec -i oliver_postgres pg_restore -U postgres -d oliver --clean pre_migration.dump`.
6. **Failed PostgreSQL Startup Recovery:**
   If the container fails to start:
   - Check port conflicts (port 5432 already occupied on Windows host).
   - Check file permission errors on Windows Docker volume mounts.
   - Check PostgreSQL log output: `docker compose logs postgres`.
7. **Application Rollback (Pre-Cutover):**
   If rollback occurs before production cutover, simply reset `DATABASE_URL` in root `.env` to SQLite.
8. **Post-Cutover Delta Reconciliation (Post-Cutover Emergency Rollback):**
   If an emergency rollback to SQLite is mandatory after PostgreSQL has taken live traffic:
   - Export newly created rows from PostgreSQL:
     `SELECT * FROM messages WHERE created_at > '<cutover_timestamp>'`
     `SELECT * FROM conversations WHERE created_at > '<cutover_timestamp>'`
     `SELECT * FROM users WHERE created_at > '<cutover_timestamp>'`
   - Run a dedicated reconciliation script (`scripts/reconcile_pg_to_sqlite.py`) to merge these delta records into `oliver_dev.db`.
   - Only after reconciliation is complete may `DATABASE_URL` be pointed back to SQLite.
9. **Docker Named Volume Recovery:**
   If `oliver_postgres_data` is corrupted:
   - Destroy the damaged volume: `docker compose down -v`.
   - Recreate volume and container: `docker compose up -d`.
   - Restore latest verified backup: `docker exec -i oliver_postgres pg_restore -U postgres -d oliver < latest.dump`.
10. **Recovery Acceptance Validation:**
    Query record counts across all 5 tables to ensure zero data loss before resuming service.

#### 4.3 Clear Distinction of Terminology
- **Application Rollback:** Changing application configuration (`DATABASE_URL`) to redirect traffic to another database engine.
- **Schema Rollback:** Using Alembic (`alembic downgrade`) to reverse specific DDL migrations within PostgreSQL.
- **Database Restoration:** Rebuilding a corrupted database cluster from a `pg_dump` physical/logical snapshot.
- **Data Synchronization:** Programmatic ETL to migrate delta records between distinct database engines to prevent split-brain data loss.

---

### Finding 5 — Reconciled, Authoritative Implementation Stage Sequence

The stage sequence has been unified into **one definitive sequence** (Stages 2.1A through 2.1G) that will be maintained consistently across all documentation and implementation phases:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Unified Implementation Stage Sequence                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
Stage 2.1A ──► Infrastructure & Container Specification (Docker, Healthcheck)
    │
Stage 2.1B ──► Python Driver & Dependency Alignment (psycopg[binary])
    │
Stage 2.1C ──► Alembic Authoritative Schema Migration Foundation (001_initial)
    │
Stage 2.1D ──► PostgreSQL Schema Deployment & Role Permission Verification
    │
Stage 2.1E ──► Backend Database Layer Adaptation & Lifespan Gating
    │
Stage 2.1F ──► Category B: PostgreSQL Backend Integration Testing
    │
Stage 2.1G ──► Desktop Regression & End-to-End System Verification
```

*(Detailed stage-by-stage specifications, preconditions, prohibited actions, deliverables, tests, and stop points are documented in Section 11).*

---

### Finding 6 — Docker PostgreSQL Health Check & Readiness

#### 6.1 The Container Running vs. Service Ready Distinction
A Docker container status of `Up` merely indicates that the container's init process (PID 1) is executing. During PostgreSQL startup:
1. PostgreSQL starts the server process.
2. It runs recovery checks and WAL replays.
3. It executes initialization scripts in `/docker-entrypoint-initdb.d/`.
4. It restarts the server to complete initialization.
5. Only then does it bind TCP port 5432 and accept client connections.

If FastAPI or an integration test attempts to connect while PostgreSQL is in phase 2 or 3, it receives an immediate `ConnectionRefusedError` or socket timeout.

#### 6.2 Health Check Specification
The `docker-compose.yml` specification must define an explicit health check utilizing PostgreSQL's native utility `pg_isready`:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -p 5432 -U oliver_app -d oliver || pg_isready -h 127.0.0.1 -p 5432 -U postgres"]
  interval: 5s
  timeout: 3s
  retries: 5
  start_period: 10s
```

#### 6.3 Health Check Parameters
- `test`: Probes PostgreSQL readiness on the loopback interface for both `oliver_app` and `postgres`.
- `interval: 5s`: Polls every 5 seconds once running.
- `timeout: 3s`: Fails probe if response takes longer than 3 seconds.
- `retries: 5`: Marks container `unhealthy` after 5 consecutive failures (25 seconds).
- `start_period: 10s`: Grace period during initial startup where failures do not count toward retries.
- **Backend Dependency Behavior:** Any containerized service depending on PostgreSQL must specify:
  ```yaml
  depends_on:
    postgres:
      condition: service_healthy
  ```

---

### Finding 7 — Independent Four-Category Testing Strategy

The original report's reliance on the 195 Stage 2E tests to validate PostgreSQL was fundamentally mistaken. Those tests validate the CustomTkinter desktop interface, speech recognition, URL classification, and telemetry; they never touch FastAPI or PostgreSQL. 

The corrected testing architecture establishes four completely isolated test categories:

```
┌────────────────────────────────────────────────────────────────────────┐
│                       Four Independent Test Categories                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│Category A: SQLite│      │Category B: PG    │      │Category C: Desk  │
│Compatibility (14)│      │Integration (New) │      │Regression (195)  │
├──────────────────┤      ├──────────────────┤      ├──────────────────┤
│ - backend/tests/ │      │ - Real PostgreSQL│      │ - tests/regress/ │
│ - In-memory DB   │      │ - Dedicated test │      │ - Local SQLite   │
│ - Mock AI        │      │   db: oliver_test│      │ - Vosk STT       │
│ - Fast unit loop │      │ - Real Alembic   │      │ - Desktop UI     │
│ - Preserves local│      │ - Real constraints│     │ - Offline verify │
└──────────────────┘      └──────────────────┘      └──────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │Category D: E2E   │
                          │System Integration│
                          ├──────────────────┤
                          │ - Desktop Client │
                          │ - FastAPI REST   │
                          │ - PostgreSQL DB  │
                          │ - Auth lifecycle │
                          │ - Offline fallbck│
                          └──────────────────┘
```

#### Category A: Backend SQLite Compatibility Tests (14 Tests)
- **Scope:** The existing 14 tests in `backend/tests/` (`test_auth.py`, `test_endpoints.py`, `test_isolation.py`, `test_tokens.py`).
- **Execution:** Runs against SQLite in-memory (`sqlite:///:memory:`) using `MockAIProvider`.
- **Purpose:** Verifies that core FastAPI business logic, JWT issuance, rate limiting, and user isolation remain fully functional in SQLite mode without regression.

#### Category B: Backend PostgreSQL Integration Tests (New Dedicated Suite)
- **Scope:** New test suite `backend/tests/test_postgres_integration.py`.
- **Target Database:** Connects exclusively to an isolated, disposable test database (`oliver_test`) via `psycopg`—**NEVER** against `oliver_dev.db` or the development PostgreSQL database.
- **Verifications:**
  - `psycopg` connection pooling and reconnection.
  - Execution of Alembic migrations from base to head against clean PostgreSQL.
  - Foreign key `ON DELETE CASCADE` behavior in PostgreSQL.
  - Unique constraint violations and transaction rollback integrity.
  - Token rotation and concurrent session handling.
  - Cross-user data isolation.

#### Category C: Desktop Regression Tests (195 Baseline Tests)
- **Scope:** The complete 195-test suite verified in Stage 2E across 10 suites (`test_stage1_browser_routing.py`, `test_stage2a_vosk_confidence.py`, `test_stage2b_cockpit_telemetry.py`, `test_stage2c_url_confirmation.py`, `test_stage2d_dual_wake_phrases.py`, `test_stage2e_integration_reliability.py`, `test_voice_pipeline.py`, etc.).
- **Execution:** Runs locally; zero network or backend dependency.
- **Purpose:** Proves beyond doubt that `database/oliver.db`, desktop speech processing, CustomTkinter UI, and browser security remain 100% operational and undisturbed.

#### Category D: End-to-End System Integration Tests
- **Scope:** Integrated execution using `desktop.api_client.client.OLIVERBackendClient` connected to a running FastAPI server backed by PostgreSQL.
- **Verifications:**
  - Login → Access Token Storage (Windows Credential Manager / DPAPI) → Refresh Token Rotation.
  - Chat execution → Message persistence in PostgreSQL `messages` table → Response round-trip.
  - Graceful degradation: Stopping PostgreSQL causes FastAPI to return typed errors; desktop client triages to `BackendServerError` / `BackendConnectionError` and safely falls back to local execution without crashing.

---

## 6. Corrected PostgreSQL / Docker Architecture

### 6.1 Docker Compose Specification (Proposed — Illustrative)

```yaml
# docker-compose.yml (PROPOSED SPECIFICATION — DO NOT CREATE YET)
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    container_name: oliver_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: oliver
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD}
      APP_USER: oliver_app
      APP_PASSWORD: ${POSTGRES_APP_PASSWORD}
      MIGRATOR_USER: oliver_migrator
      MIGRATOR_PASSWORD: ${POSTGRES_MIGRATOR_PASSWORD}
    ports:
      - "127.0.0.1:5432:5432"   # Loopback only; zero external exposure
    volumes:
      - oliver_postgres_data:/var/lib/postgresql/data
      - ./backend/docker/init-db.sh:/docker-entrypoint-initdb.d/01-init-db.sh:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -p 5432 -U oliver_app -d oliver || pg_isready -h 127.0.0.1 -p 5432 -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s

volumes:
  oliver_postgres_data:
    name: oliver_postgres_data
```

### 6.2 Initialization Script Architecture (`01-init-db.sh`)

When the volume is fresh, this script executes inside the container under the `postgres` superuser:

```bash
#!/bin/bash
# 01-init-db.sh (PROPOSED SPECIFICATION — DO NOT CREATE YET)
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- 1. Create Migration Role (DDL Owner)
    CREATE USER $MIGRATOR_USER WITH ENCRYPTED PASSWORD '$MIGRATOR_PASSWORD';
    GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $MIGRATOR_USER;
    ALTER SCHEMA public OWNER TO $MIGRATOR_USER;

    -- 2. Create Application Runtime Role (DML Only)
    CREATE USER $APP_USER WITH ENCRYPTED PASSWORD '$APP_PASSWORD';
    GRANT CONNECT ON DATABASE $POSTGRES_DB TO $APP_USER;
    GRANT USAGE ON SCHEMA public TO $APP_USER;

    -- 3. Set Default Privileges for Tables Created by Migrator
    ALTER DEFAULT PRIVILEGES FOR ROLE $MIGRATOR_USER IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $APP_USER;
    ALTER DEFAULT PRIVILEGES FOR ROLE $MIGRATOR_USER IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO $APP_USER;
EOSQL
```

---

## 7. Security and Credentials Management

### 7.1 Security Posture Assessment

| Security Dimension | Local Development Mode | Production Deployment Mode | Action for Phase 2.1 |
|---|---|---|---|
| **PostgreSQL Port Binding** | `127.0.0.1:5432` (Loopback) | Private Docker Network / Internal VPC | Bind strictly to `127.0.0.1` |
| **Database Passwords** | Local `.env` secrets | Secret Manager / HashiCorp Vault | Read from root `.env` (gitignored) |
| **Application Privileges** | Non-superuser DML role (`oliver_app`) | Non-superuser DML role (`oliver_app`) | Enforced via init script |
| **Migration Privileges** | Schema owner (`oliver_migrator`) | Dedicated CI/CD deployer role | Enforced via init script |
| **CORS Origins** | Currently `["*"]` in dev config | Explicit whitelisted origins | Warn and tighten before release |
| **JWT Secret** | `JWT_SECRET_KEY` in `.env` | Cryptographically random 256-bit key | Mandate in `.env.example` |
| **Connection SSL** | `sslmode=prefer` (loopback) | `sslmode=require` / `verify-full` | Defer `verify-full` to prod |

### 7.2 Credentials Redaction Protocol
- In `backend/app/core/logging.py`, ensure database connection strings are never logged directly.
- In FastAPI exception handlers, ensure raw `psycopg.OperationalError` exceptions (which may contain connection strings) are sanitized before being returned to clients as HTTP 500 errors.

---

## 8. Alembic Migration Strategy

### 8.1 Current Alembic State
- `backend/alembic/env.py` is properly configured with `from backend.app.models import User, RefreshToken, Conversation, Message, Device`.
- `target_metadata = Base.metadata` is set correctly.
- `backend/alembic.ini` points to `backend/alembic`.
- `backend/alembic/versions/` contains only `.gitkeep`.

### 8.2 Migration Generation & Validation Flow
In Stage 2.1C:
1. Ensure the PostgreSQL container is running and healthy.
2. Run Alembic autogenerate connecting with the `oliver_migrator` credentials:
   `alembic -c backend/alembic.ini revision --autogenerate -m "001_initial_schema"`
3. **Manual Code Inspection of Generated Revision:**
   - Verify that all 5 tables (`users`, `refresh_tokens`, `conversations`, `messages`, `devices`) are generated with matching column types.
   - Verify that foreign key constraints specify `ondelete="CASCADE"`.
   - Verify that unique constraints (`users.email`, `refresh_tokens.token_hash`) and indexes are properly created.
   - Verify that SQLite-specific PRAGMAs or quirks are absent.
4. Test migration upgrade and downgrade against disposable test database (`oliver_test`):
   `alembic -c backend/alembic.ini upgrade head`
   `alembic -c backend/alembic.ini downgrade base`
   `alembic -c backend/alembic.ini upgrade head`

---

## 9. SQLite Coexistence Strategy

### 9.1 Desktop vs. Backend Boundary
- **Desktop SQLite (`database/oliver.db`):** Permanent, unmigrated, local-only offline store. Contains FTS5 virtual tables, memory, notes, tasks. Never talks to PostgreSQL.
- **Backend SQLite (`backend/oliver_dev.db`):** Maintained during transition as a fallback store. Once PostgreSQL is verified in Stage 2.1G, it will be retained as a cold backup.
- **API Client:** The desktop client (`desktop/api_client/`) interacts with the backend strictly via HTTP REST. The database engine driving FastAPI is completely transparent to the desktop application.

---

## 10. Additional Architectural Decisions

### 10.1 UUID Strategy
- **Decision:** **Retain existing `String(36)` identifiers.**
- **Rationale:** The existing models use `String(36)` storing `str(uuid.uuid4())`. PostgreSQL supports `VARCHAR(36)` natively with full indexing performance. Converting to native PostgreSQL `UUID` type would require custom type compilation across dialects, schema migrations on foreign keys, and adjustments in Pydantic serializers with zero user-facing benefit. Defer native UUID optimization to a future phase.

### 10.2 Preferences Column Strategy
- **Decision:** **Retain existing `Text` storing serialized JSON strings.**
- **Rationale:** `User.preferences` is currently handled as serialized JSON text with application-level validation. Migrating to PostgreSQL `JSONB` in Phase 2.1 would introduce unnecessary cross-dialect friction for SQLite test fixtures. Retain `Text` for Phase 2.1; evaluate `JSONB` in Phase 2.2 when structured querying of preferences is required.

### 10.3 Existing Development Data Recommendation
- **Decision:** **Start with a fresh, clean database in PostgreSQL.**
- **Rationale:** `backend/oliver_dev.db` currently contains only 3 test users, 6 refresh tokens, and 3 messages. Migrating these transient test records adds unnecessary ETL complexity and risk of schema divergence. The original `backend/oliver_dev.db` will remain preserved on disk as a cold backup. If developers need accounts, they can register clean accounts via `/api/auth/register` in seconds.

### 10.4 Python 3.13.5 and `psycopg` Compatibility
- **Evaluation:** Python 3.13.5 is installed on Windows 11.
- **Dependency Choice:** Specify `psycopg[binary]>=3.2.0` in `backend/requirements.txt`.
- **Compatibility Verification:** The `psycopg` v3 binary distribution provides official pre-compiled C-extension wheels (`cp313-cp313-win_amd64.whl`) on PyPI for Python 3.13 on Windows. This eliminates the need for Visual C++ Build Tools or local `libpq` installations on Windows.

---

## 11. Authoritative Implementation Stage Sequence

Every implementation stage is structured with strict preconditions, authorized actions, prohibitions, tests, and stop points:

### Stage 2.1A — Infrastructure & Container Specification
- **Scope:** Author `docker-compose.yml`, container initialization script (`backend/docker/init-db.sh`), and update `.env.example`.
- **Preconditions:** Docker Desktop for Windows installed, running, and verified via `docker --version` and `docker compose version`.
- **Permitted Changes:** Create `docker-compose.yml`, create `backend/docker/init-db.sh`, update root `.env.example`.
- **Prohibited Changes:** Modifying Python files, installing packages, modifying SQLite databases.
- **Deliverables:** Valid Compose file with health check, initialization script with 3-tier roles.
- **Verification:** Execute `docker compose up -d`; verify `docker compose ps` shows `healthy` after start period.
- **Failure Conditions:** Container crashes, port 5432 conflict, healthcheck fails.
- **Rollback:** `docker compose down -v`.
- **Stop Point:** Container healthy. **STOP AND AWAIT USER APPROVAL.**

---

### Stage 2.1B — Python Driver & Dependency Alignment
- **Scope:** Add `psycopg[binary]>=3.2.0` to `backend/requirements.txt`; install into local environment.
- **Preconditions:** Stage 2.1A PASS.
- **Permitted Changes:** Modify `backend/requirements.txt`.
- **Prohibited Changes:** Modifying application source code or models.
- **Deliverables:** `backend/requirements.txt` updated; `psycopg` available in Python runtime.
- **Verification:** Execute `python -c "import psycopg; print(psycopg.__version__)"`.
- **Failure Conditions:** Wheel installation failure, DLL missing errors.
- **Rollback:** Revert `backend/requirements.txt`, run `pip uninstall psycopg`.
- **Stop Point:** Driver imported successfully. **STOP AND AWAIT USER APPROVAL.**

---

### Stage 2.1C — Alembic Authoritative Schema Migration Foundation
- **Scope:** Configure `backend/alembic.ini` and `backend/alembic/env.py` to support PostgreSQL credentials; generate initial migration `001_initial_schema.py`.
- **Preconditions:** Stage 2.1B PASS, PostgreSQL container running.
- **Permitted Changes:** Modify `backend/alembic.ini`, modify `backend/alembic/env.py`, create `backend/alembic/versions/001_initial_schema.py`.
- **Prohibited Changes:** Executing migration against database, modifying ORM models.
- **Deliverables:** Valid migration script representing all 5 tables, constraints, and indexes.
- **Verification:** Static review of generated migration file; generate SQL offline via `alembic upgrade head --sql`.
- **Failure Conditions:** Autogenerate omits models, syntax errors in migration script.
- **Rollback:** Delete generated migration file.
- **Stop Point:** Migration script validated. **STOP AND AWAIT USER APPROVAL.**

---

### Stage 2.1D — PostgreSQL Schema Deployment & Role Permission Verification
- **Scope:** Execute `alembic upgrade head` using `oliver_migrator` credentials; verify tables, constraints, indexes, and `oliver_app` permissions in PostgreSQL.
- **Preconditions:** Stage 2.1C PASS.
- **Permitted Changes:** Execute DDL against PostgreSQL container. Zero filesystem changes.
- **Prohibited Changes:** Modifying SQLite databases, modifying application code.
- **Deliverables:** PostgreSQL database containing all 5 tables, `alembic_version` stamped, `oliver_app` permissions verified.
- **Verification:** Run SQL inspection script verifying table list, foreign keys, and testing `oliver_app` DML success and DDL denial.
- **Failure Conditions:** Migration failure, permission denied errors.
- **Rollback:** `alembic downgrade base` or recreate Docker volume.
- **Stop Point:** Schema and permissions verified. **STOP AND AWAIT USER APPROVAL.**

---

### Stage 2.1E — Backend Database Layer Adaptation & Lifespan Gating
- **Scope:** Update `backend/app/main.py` lifespan to gate `create_all()` strictly to SQLite dev mode; adapt `backend/app/core/database.py` for connection pooling (`pool_recycle=1800`, dialect-aware args).
- **Preconditions:** Stage 2.1D PASS.
- **Permitted Changes:** Modify `backend/app/main.py`, modify `backend/app/core/database.py`.
- **Prohibited Changes:** Altering API router endpoints or authentication schemas.
- **Deliverables:** Codebase supporting both SQLite and PostgreSQL with proper connection pooling and gated DDL.
- **Verification:** Run Category A tests (`backend/tests/`) against in-memory SQLite (14/14 PASS); test engine connection against PostgreSQL.
- **Failure Conditions:** Regression in Category A tests, connection failure to PostgreSQL.
- **Rollback:** Revert changes to `main.py` and `database.py`.
- **Stop Point:** Dual-dialect engine operational. **STOP AND AWAIT USER APPROVAL.**

---

### Stage 2.1F — Category B: PostgreSQL Backend Integration Testing
- **Scope:** Create and execute dedicated Category B integration suite `backend/tests/test_postgres_integration.py` against disposable `oliver_test` database.
- **Preconditions:** Stage 2.1E PASS.
- **Permitted Changes:** Create `backend/tests/test_postgres_integration.py`.
- **Prohibited Changes:** Running destructive tests against development databases.
- **Deliverables:** Comprehensive integration suite verifying auth, token rotation, user isolation, and rollback in PostgreSQL.
- **Verification:** Execute `python -m pytest backend/tests/test_postgres_integration.py` (All PASS).
- **Failure Conditions:** Constraint mismatch, transaction deadlock, session leak.
- **Rollback:** Fix tests or remove test file.
- **Stop Point:** Category B integration tests passing. **STOP AND AWAIT USER APPROVAL.**

---

### Stage 2.1G — Desktop Regression & End-to-End System Verification
- **Scope:** Run Category C desktop regression suite (195 tests) to confirm zero desktop disruption; run Category D end-to-end integration tests (`desktop.api_client` talking to FastAPI over PostgreSQL).
- **Preconditions:** Stage 2.1F PASS.
- **Permitted Changes:** Create optional `tests/integration/test_e2e_backend.py`. Zero modifications to existing tests or desktop database.
- **Prohibited Changes:** Modifying `database/oliver.db`.
- **Deliverables:** Full verification report demonstrating all 4 test categories passing.
- **Verification:**
  - Category A: 14/14 PASS
  - Category B: PostgreSQL Integration PASS
  - Category C: 195/195 PASS
  - Category D: End-to-End PASS
- **Failure Conditions:** Any test failure in any category.
- **Rollback:** Revert `.env` `DATABASE_URL` to SQLite.
- **Stop Point:** Phase 2.1 Complete. **STOP AND PREPARE AUDIT REPORT.**

---

## 12. Corrected File-Change Inventory

| Target File Path | Action | Stage | Purpose / Description | Security / Credential Status | DB Impact |
|---|---|---|---|---|---|
| `docker-compose.yml` | **CREATE** | 2.1A | PostgreSQL 16-alpine container, health check, volumes | Uses `${POSTGRES_*_PASSWORD}` vars | None |
| `backend/docker/init-db.sh` | **CREATE** | 2.1A | 3-tier role initialization script | Uses env vars inside container | None |
| `.env.example` | **MODIFY** | 2.1A | Add PostgreSQL credential placeholders and URL | Template only; no real secrets | None |
| `backend/requirements.txt` | **MODIFY** | 2.1B | Add `psycopg[binary]>=3.2.0` | Dependency manifest | None |
| `backend/alembic.ini` | **MODIFY** | 2.1C | Configure script location and remove static SQLite URL | Configuration | None |
| `backend/alembic/env.py` | **MODIFY** | 2.1C | Ensure migration role URL resolution from settings | Reads from settings | None |
| `backend/alembic/versions/001_initial_schema.py` | **CREATE** | 2.1C | Initial schema revision for 5 tables | DDL migration code | None |
| `backend/app/main.py` | **MODIFY** | 2.1E | Gate `create_all()` to SQLite dev mode only | Application lifecycle | Protects PG |
| `backend/app/core/database.py` | **MODIFY** | 2.1E | Dialect-aware pooling (`pool_recycle=1800`) | Engine configuration | Dual-dialect |
| `backend/tests/test_postgres_integration.py` | **CREATE** | 2.1F | Dedicated Category B PostgreSQL integration suite | Automated test file | Uses `oliver_test` |
| `.env` (Root) | **MODIFY** | 2.1D | Set `DATABASE_URL` and PostgreSQL passwords | **Contains local secrets; Gitignored** | Switches runtime |
| `database/oliver.db` | **NO CHANGE** | All | Desktop local SQLite store | Preserved untouched | **ZERO IMPACT** |
| `backend/oliver_dev.db` | **NO CHANGE** | All | Backend SQLite store (cold backup) | Preserved untouched | **ZERO IMPACT** |
| `database/oliver.db-shm` | **NO CHANGE** | All | Pre-existing Git tracked deletion | Preserved untouched | **ZERO IMPACT** |
| `database/oliver.db-wal` | **NO CHANGE** | All | Pre-existing Git tracked deletion | Preserved untouched | **ZERO IMPACT** |

---

## 13. Testing and Acceptance Strategy

### 13.1 Objective Acceptance Criteria Checklist

| Criterion ID | Objective Acceptance Requirement | Verification Method | Status |
|---|---|---|---|
| **AC-01** | Docker Engine & Compose installed and operational | `docker compose version` | **NOT VERIFIED** (Blocked) |
| **AC-02** | PostgreSQL container starts and passes health check | `docker compose ps` shows `healthy` | **NOT VERIFIED** (Pending 2.1A) |
| **AC-03** | 3-tier roles created with least privilege | `\du` in psql; `oliver_app` DDL rejected | **NOT VERIFIED** (Pending 2.1A) |
| **AC-04** | `psycopg` imports cleanly in Python 3.13.5 | `python -c "import psycopg"` exits 0 | **NOT VERIFIED** (Pending 2.1B) |
| **AC-05** | Initial Alembic revision generated and validated | `alembic upgrade head --sql` exits 0 | **NOT VERIFIED** (Pending 2.1C) |
| **AC-06** | All 5 tables created in PostgreSQL with constraints | Schema query in PostgreSQL | **NOT VERIFIED** (Pending 2.1D) |
| **AC-07** | `alembic_version` table exists and stamped at head | `SELECT * FROM alembic_version` | **NOT VERIFIED** (Pending 2.1D) |
| **AC-08** | `create_all()` strictly disabled in PostgreSQL mode | Lifespan inspection & startup log | **NOT VERIFIED** (Pending 2.1E) |
| **AC-09** | Category A tests (14 tests) pass on in-memory SQLite | `pytest backend/tests` exits 0 | ✅ **VERIFIED** (14/14 PASS) |
| **AC-10** | Category B tests pass on PostgreSQL (`oliver_test`) | `pytest backend/tests/test_postgres*` | **NOT VERIFIED** (Pending 2.1F) |
| **AC-11** | Category C desktop regression suite passes (195 tests) | Stage 2E regression suites exit 0 | ✅ **VERIFIED** (195/195 PASS) |
| **AC-12** | Desktop local SQLite (`database/oliver.db`) unchanged | File hash & schema check | ✅ **VERIFIED** (Unmodified) |
| **AC-13** | Category D end-to-end auth & chat succeeds | Client integration test exits 0 | **NOT VERIFIED** (Pending 2.1G) |
| **AC-14** | PostgreSQL backup and restore verified | `pg_dump` and `pg_restore` dry run | **NOT VERIFIED** (Pending 2.1G) |
| **AC-15** | Post-cutover delta reconciliation verified | Dry-run script execution | **NOT VERIFIED** (Pending 2.1G) |

---

## 14. Risks and Unresolved Decisions

### 14.1 Technical Risk Assessment

| Risk Description | Probability | Severity | Mitigation Strategy |
|---|---|---|---|
| **Windows Hyper-V / WSL2 Conflict** | Medium | High | Docker Desktop on Windows requires WSL2 backend. Ensure WSL2 Linux kernel update package is applied prior to Docker Desktop installation. |
| **Port 5432 Local Conflict** | Medium | Medium | If the developer machine has a native PostgreSQL service already running, map container port to `127.0.0.1:5433:5432` and adjust `DATABASE_URL`. |
| **Premature Connection on Startup** | Low | High | Fully mitigated by `healthcheck` with `pg_isready` and backend dependency condition `service_healthy`. |
| **Accidental Secret Commit** | Low | Critical | Root and nested `.env` confirmed gitignored. Pre-commit check verifies no credential strings exist in staged diffs. |
| **Desktop FTS5 Disruption** | Zero | Critical | Mitigated by complete architectural isolation: `database/oliver.db` is not included in Phase 2.1 scope. |

### 14.2 Items Requiring Explicit User Decisions

1. **Local Host Port Selection:** Standard port `5432` is proposed. User must confirm whether `5432` is currently free on their Windows host or if an alternate port (e.g., `5433`) is preferred.
2. **Docker Desktop Licensing:** User must confirm that Docker Desktop terms (free for personal/small business use) align with their operating environment.

---

## 15. Final Readiness Verdict

### Verdict: **NOT READY**

**Justification:**  
While the architectural design, security controls, Alembic migration strategy, and testing definitions are now fully resolved and production-grade, the physical environment does **NOT** meet the minimum operational requirements to begin implementation:

1. **Docker Desktop is not installed on the host system** (`docker` command is unrecognized). PostgreSQL cannot be provisioned or executed.
2. **`psycopg` is not installed** in the Python environment, preventing any database driver connectivity.
3. **Stage 2.1 implementation authorization has not been granted.**

The status will transition to **READY FOR IMPLEMENTATION** once Docker Desktop is installed, verified, and explicit authorization to proceed with Stage 2.1A is provided by the user.

---

## 16. Implementation Authorization Boundary

**MANDATORY ENFORCEMENT:**  
This document represents a **planning and readiness review only**. 

- **NO** implementation work has been executed.
- **NO** files in the codebase, tests, configuration, or databases have been created, modified, or deleted.
- **NO** packages have been installed.
- **NO** background services or containers have been started.
- **NO** Git state has been altered.

**NEXT ACTION REQUIRED FROM USER:**  
1. Review and approve this corrected planning document.
2. Install Docker Desktop for Windows.
3. Explicitly issue the implementation instruction: *"Proceed with Phase 2.1 Stage 2.1A"*.

---

*Report authored strictly in READ-ONLY mode by Antigravity Planning Agent | 2026-11-14*
