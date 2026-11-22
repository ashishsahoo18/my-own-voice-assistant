# OLIVER 3.0 — Phase 2.1A2 PostgreSQL Roles & Permissions Readiness Report

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A2_POSTGRESQL_ROLES_PERMISSIONS_READINESS_REPORT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Migration  
**Stage:** 2.1A.2 — PostgreSQL Roles & Permissions (Planning & Audit)  
**Report Date:** 2026-11-22  
**Audit Mode:** STRICTLY READ-ONLY — Zero implementation, zero source modification  
**Preceding Stage:** 2.1A.1 — PostgreSQL Environment & Configuration (commit `d466b4b`)  
**HEAD at Audit Time:** `f24b231` ("Create OLIVER_3_PHASE_2_1A1_IMPLEMENTATION_REPORT.md")

---

## 1. Executive Summary

This report provides a complete least-privilege PostgreSQL role architecture for OLIVER 3.0, grounded in direct inspection of all source files. Every claim about the codebase references a specific file and line number. Recommendations are clearly distinguished from verified facts.

**Key findings:**

1. **The runtime application (`oliver_app_user`) must NOT own the schema.** It performs only DML (SELECT, INSERT, UPDATE, DELETE). Schema ownership and DDL must belong to the migration role only.
2. **Alembic currently uses `settings.DATABASE_URL`** — the same URL the application uses. This must be changed: migration execution requires a separate credential with elevated privileges. The URL must be supplied via a separate environment variable (e.g. `MIGRATION_DATABASE_URL`), not by reusing `DATABASE_URL`.
3. **The `conftest.py` guard already enforces the correct test database name and user** (`oliver_test`, `oliver_test_user`) and verifies that the database owner is `oliver_migrator` and the schema owner is `oliver_test_user`. The role design must match these already-encoded requirements precisely.
4. **Health check exposes a live `SELECT 1`** via the runtime role — confirming the runtime role needs CONNECT + schema USAGE + SELECT on the `public` schema's tables.
5. **No role design currently exists in the repository.** No SQL provisioning scripts, `docker-entrypoint-initdb.d/` files, or role-creation tooling are present. These are the deliverables for Stage 2.1A.2 implementation.
6. **Android clients never connect directly to PostgreSQL.** They connect through the FastAPI backend API only. No Android database role is needed.

**Final readiness verdict: READY WITH CONDITIONS**

Stage 2.1A.2 implementation can proceed upon authorization. Conditions are documented in Section 14.

---

## 2. Verified Repository Findings

### 2.1 Git State

| Property | Value |
|---|---|
| Active Branch | `main` |
| HEAD Commit | `f24b231` |
| HEAD Message | `Create OLIVER_3_PHASE_2_1A1_IMPLEMENTATION_REPORT.md` |
| Working Tree | **Clean — 0 tracked modifications, 0 untracked files** |

### 2.2 Database Integrity

| File | Size (Bytes) | Last Modified | Status |
|---|---|---|---|
| `database/oliver.db` | 192,512 | 07-11-2026 19:38:26 | **INTACT** |
| `backend/oliver_dev.db` | 94,208 | 07-11-2026 18:12:44 | **INTACT** |

### 2.3 Stage 2.1A.0 & 2.1A.1 Preservation

- `backend/app/main.py` (211 lines): `_verify_startup_schema()` with fail-closed PostgreSQL Alembic head check and `OperationalError` handling confirmed present.
- `backend/tests/conftest.py` (435 lines): Full pre-import isolation guard confirmed present. `oliver_migrator` and `oliver_test_user` ownership assertions at lines 369 and 383 are **ACTIVE REQUIREMENTS** that the role design must satisfy.
- `backend/app/core/database.py` (61 lines): Dialect-conditional pool parameters via `make_url()` confirmed present.
- `backend/alembic.ini`: Hardcoded SQLite URL removed; mandatory comment requiring `DATABASE_URL` env var confirmed present.

---

## 3. Current Architecture (Verified)

### 3.1 Configuration (`backend/app/core/config.py`)

**Evidence — Lines 31–34:**
```python
DATABASE_URL: str = Field(
    default=f"sqlite:///{BACKEND_DIR / 'oliver_dev.db'}",
    description="Database connection URL",
)
```

Resolution order (highest to lowest priority):
1. `DATABASE_URL` OS environment variable
2. `backend/.env` (does not exist — skipped)
3. Root `.env` (exists; no `DATABASE_URL` → skipped)
4. Default: `sqlite:///backend/oliver_dev.db`

**Critical finding:** There is a single `DATABASE_URL` field. Alembic currently reads from `settings.DATABASE_URL` — the same URL used by the FastAPI engine. This is a **design defect** that must be resolved in Stage 2.1A.2: the migration role requires a separate, more-privileged credential than the runtime role.

### 3.2 Database Engine (`backend/app/core/database.py`)

**Evidence — Lines 13–36:**
- `make_url(settings.DATABASE_URL)` → dialect detected as `"sqlite"` (current default)
- PostgreSQL path: `pool_size=5`, `max_overflow=10`, `pool_timeout=30`, `pool_recycle=1800`, `connect_timeout=10`
- Engine created with `pool_pre_ping=True`

The `engine` object is the single application runtime connection. All FastAPI routes receive sessions from `SessionLocal` → this is the only identity that makes DML calls at runtime.

### 3.3 Alembic (`backend/alembic/env.py`)

**Evidence — Lines 23 and 37:**
```python
# Offline mode:
url = settings.DATABASE_URL

# Online mode:
configuration["sqlalchemy.url"] = settings.DATABASE_URL
```

Both offline and online migration modes read **the same `DATABASE_URL` as the application**. This means the Alembic migration would currently run as `oliver_app_user` — the runtime application user. This is **incorrect** for a least-privilege architecture:

- `oliver_app_user` must NOT have DDL privileges.
- Alembic requires CREATE TABLE, ALTER TABLE, DROP TABLE — which must belong to `oliver_migrator` only.
- **Required change (Stage 2.1A.2 scope):** Add a separate `MIGRATION_DATABASE_URL` environment variable and use it in `alembic/env.py`. This is a critical design decision that must be reflected in the implementation plan.

### 3.4 Startup Safety (`backend/app/main.py`)

**Evidence — Lines 69–137:**

The PostgreSQL startup path in `_verify_startup_schema()`:
1. Opens a connection with `engine.connect()` — uses `DATABASE_URL` credentials (runtime role)
2. Creates a `MigrationContext` to read `alembic_version` table
3. Verifies single migration head from script directory matches current DB revision

**Implication for role design:** The runtime role (`oliver_app_user`) must have SELECT on the `alembic_version` table (created by Alembic during migration). This is a narrow, read-only need and is correctly satisfied by a DML-only grant.

### 3.5 Database Access Patterns (All Routers & Services)

Surveyed all 6 routers and 3 service files. Access pattern summary:

| Table | SELECT | INSERT | UPDATE | DELETE | Evidence |
|---|---|---|---|---|---|
| `users` | ✅ | ✅ | ✅ (preferences) | ❌ (cascade only) | `auth_service.py:32,53`, `user.py:36-49` |
| `refresh_tokens` | ✅ | ✅ | ✅ (revoke) | ❌ (cascade only) | `auth_service.py:98,110,134` |
| `conversations` | ✅ | ✅ | ❌ | ❌ (cascade only) | `chat_service.py:68,84` |
| `messages` | ✅ | ✅ | ❌ | ❌ (cascade only) | `chat_service.py:94,107,169` |
| `devices` | ✅ | ✅ | ✅ (last_active_at) | ❌ (cascade only) | `devices.py:29,46,39` |
| `alembic_version` | ✅ | ❌ | ❌ | ❌ | `main.py:98-100` |

> [!NOTE]
> No application code calls DELETE directly. All deletions occur through SQLAlchemy cascade behavior when a parent row (e.g. `users`) is deleted. The runtime role still needs DELETE privileges because the ORM-issued cascade deletes flow through the application connection. However, there is currently no user-deletion endpoint in the codebase — this is a future concern.

**Health check:** `health.py:22` executes `SELECT 1` via the runtime engine — confirming CONNECT and EXECUTE SELECT are required for the runtime role.

**Sequence access:** All PKs use Python-side `uuid.uuid4()`. No server-side `nextval()` calls. **No sequence access is needed by the runtime role.** However, Alembic may generate sequences for auto-increment types if any future migration introduces them. The migration role should retain sequence creation rights.

### 3.6 Test Configuration (`backend/tests/conftest.py`)

The following hardcoded role and database requirements are **enforced at test runtime** (lines 125–386):

| Requirement | Enforced Value | Location |
|---|---|---|
| Test database name | `oliver_test` | Line 125–127 |
| Test username | `oliver_test_user` | Line 130–132 |
| Test host | `127.0.0.1` or `localhost` | Line 135–137 |
| Test port | `5432` | Line 140–142 |
| Test superuser | MUST be `False` | Line 353–355 |
| Test user is `pg_database_owner` | MUST be `False` | Line 355–356 |
| Database owner | MUST be `oliver_migrator` | Line 369 |
| Public schema owner | MUST be `oliver_test_user` | Line 383 |

> [!IMPORTANT]
> These are not aspirational targets — they are live security assertions that will cause Category B tests to `SECURITY ABORT` if they fail. The PostgreSQL provisioning scripts must create the roles and databases in exact conformance with these values.

### 3.7 `.gitignore` Analysis

**Evidence — `.gitignore` lines 1–4:**
```
.env
.env.*
!.env.example
```

`.env` and all `.env.*` variants are excluded from Git. `backend/.env` (which will contain real credentials) will correctly never be committed. ✅

**Gap:** `.gitignore` uses `*.db` (line 25) which correctly excludes both SQLite databases. No PostgreSQL dump files (`*.dump`, `*.sql.gz`) are excluded. This should be added before backup scripts are created in Stage 2.1A.6.

---

## 4. Proposed PostgreSQL Role Architecture

### 4.1 Role Design Rationale

OLIVER requires exactly **four roles** for the local Docker development deployment. A fifth role for backup is optional for local development but recommended for the design. The roles are:

| Role Name | Purpose | Superuser | Login | Owns Schema | Can DDL |
|---|---|---|---|---|---|
| `oliver_admin` | Bootstrap only: creates other roles and databases | No (see note) | Yes (bootstrap only) | No | Yes (via SUPERUSER for setup) |
| `oliver_migrator` | Runs Alembic migrations; owns the databases and schema | No | Yes | Yes | Yes |
| `oliver_app_user` | FastAPI runtime application | No | Yes | No | No |
| `oliver_test_user` | Category B integration testing | No | Yes | Yes (test schema only) | No (DML only) |
| `oliver_backup` | Logical backup (pg_dump) | No | No (or Yes, restricted) | No | No |

### 4.2 Role Decision Justifications

**Why `oliver_migrator` owns the database and schema, not `oliver_admin`:**
`conftest.py` line 369 asserts `db_owner == "oliver_migrator"`. This is an active enforcement. The provisioning must make `oliver_migrator` the owner of both `oliver_db` and `oliver_test`. The admin role is only needed during initial bootstrapping.

**Why `oliver_app_user` must NOT own the schema:**
Schema ownership grants implicit CREATE rights on the schema. If `oliver_app_user` owns `public`, it can create and drop tables — which violates the principle of least privilege and would allow application bugs or SQL injection to alter the schema. The runtime role must be strictly DML-only.

**Why `oliver_test_user` owns the `public` schema in `oliver_test`:**
`conftest.py` line 383 asserts `schema_owner == "oliver_test_user"`. This is an active enforcement specifically for the test database. The test user needs to own the schema in the test database so it can create/drop tables during test setup (via `conftest.py`'s `init_test_db` fixture which calls `Base.metadata.create_all(bind=test_engine)`). This is intentionally different from the production setup where `oliver_app_user` has no DDL.

> [!WARNING]
> The `init_test_db` fixture in `conftest.py` (lines 405–410) calls `Base.metadata.create_all(bind=test_engine)` and `Base.metadata.drop_all(bind=test_engine)`. In Category B tests, `test_engine` uses the `oliver_test_user` credential. This means `oliver_test_user` MUST have CREATE TABLE / DROP TABLE privileges on `oliver_test`. This is why `oliver_test_user` owns the schema in the test database.

**Why `oliver_admin` should NOT be a PostgreSQL superuser in production:**
For local Docker development, using the `postgres` superuser for bootstrap is pragmatic and acceptable. For Stage 2.1A.2 implementation, the provisioning script can run as the `postgres` superuser (available inside the Docker container via `docker exec`). No separate `oliver_admin` login role is strictly necessary for local dev — it is a future production concern. For simplicity, Stage 2.1A.2 will document the bootstrap approach using the container's `postgres` superuser.

**Why `oliver_backup` does not need login by default:**
For local development, `pg_dump` can be run as the `postgres` superuser via `docker exec`. A dedicated backup role is a production/Stage 2.1A.6 concern. It is included in the design for completeness but not required for Stage 2.1A.2.

**Android client:** The Android mobile client connects exclusively through the FastAPI REST API. It has no direct database connection. No Android-specific database role is needed.

---

## 5. Least-Privilege Permission Matrix

### 5.1 Production Database (`oliver_db`)

| Permission | `oliver_migrator` | `oliver_app_user` | `oliver_backup` | Notes |
|---|---|---|---|---|
| CONNECT to `oliver_db` | ✅ | ✅ | ✅ | Backup needs CONNECT for `pg_dump` |
| Schema `public` USAGE | ✅ (owns it) | ✅ | ✅ | |
| SELECT on all tables | ✅ | ✅ | ✅ | App needs SELECT; backup needs SELECT for dump |
| INSERT on all tables | ✅ | ✅ | ❌ | Backup never writes |
| UPDATE on all tables | ✅ | ✅ | ❌ | |
| DELETE on all tables | ✅ | ✅ | ❌ | Cascade deletes flow through app role |
| CREATE TABLE / ALTER / DROP | ✅ (via ownership) | ❌ | ❌ | Only migrator can alter schema |
| CREATE INDEX | ✅ | ❌ | ❌ | |
| TRUNCATE | ❌ | ❌ | ❌ | Never needed |
| Sequence CREATE | ✅ | ❌ | ❌ | Currently no sequences; reserved for future |
| Sequence USAGE (`nextval`) | ✅ | ❌ | ❌ | No sequences used (Python-side UUIDs) |
| SELECT on `alembic_version` | ✅ | ✅ | ❌ | App needs this for startup head check |
| INSERT/UPDATE on `alembic_version` | ✅ | ❌ | ❌ | Only Alembic writes version table |
| Role management | ❌ | ❌ | ❌ | Only `postgres` superuser |
| `pg_dump` execution | ❌ (not needed) | ❌ | ✅ | Backup reads all tables |
| `pg_restore` / `psql` restore | ❌ | ❌ | ❌ | Only `postgres` superuser for restore |

### 5.2 Test Database (`oliver_test`)

| Permission | `oliver_migrator` | `oliver_test_user` | Notes |
|---|---|---|---|
| CONNECT to `oliver_test` | ✅ | ✅ | |
| Own `oliver_test` database | ✅ | ❌ | Enforced by `conftest.py` line 369 |
| Own `public` schema | ❌ | ✅ | Enforced by `conftest.py` line 383 |
| SELECT / INSERT / UPDATE / DELETE | ✅ | ✅ | Full DML for testing |
| CREATE TABLE / DROP TABLE | ✅ | ✅ (via schema ownership) | Needed by `init_test_db` fixture |
| Superuser | ❌ | ❌ | Enforced by `conftest.py` line 353 |
| `pg_database_owner` member | ❌ | ❌ | Enforced by `conftest.py` line 355 |
| Write to `oliver_db` | ❌ | ❌ | Test role must never reach prod DB |

### 5.3 Connection Limit Recommendations

| Role | CONNECTION LIMIT | Rationale |
|---|---|---|
| `oliver_migrator` | 2 | Only needed during migrations; Alembic uses NullPool |
| `oliver_app_user` | 20 | `pool_size=5`, `max_overflow=10` → max 15 active + headroom |
| `oliver_test_user` | 10 | Test runs are sequential; some parallelism needed |
| `oliver_backup` | 1 | One dump at a time |

---

## 6. Credential and Secret Security Audit

### 6.1 Environment Variable Usage

**Verified findings:**

| Variable | Currently Defined | Location | Used By |
|---|---|---|---|
| `DATABASE_URL` | In `backend/.env.example` (commented PG block) | `config.py:31` | FastAPI engine, Alembic |
| `ENVIRONMENT` | In `.env.example` | `config.py:17` | Startup guard, logging |
| `OLIVER_TEST_MODE` | Not in any `.env` — runtime only | `conftest.py:150` | Test isolation guard |
| `MIGRATION_DATABASE_URL` | **NOT DEFINED ANYWHERE** | Missing | Needed for Stage 2.1A.2 |

**Critical gap:** `MIGRATION_DATABASE_URL` does not exist. `alembic/env.py` reads `settings.DATABASE_URL` for both offline and online migration modes. This must be corrected so that migrations run as `oliver_migrator`, not as `oliver_app_user`.

### 6.2 `.env` File Security

| File | Git Status | Contains Credentials | Risk |
|---|---|---|---|
| `.env` | Excluded (`.gitignore` line 2) | Will contain real passwords | ✅ Correctly excluded |
| `.env.*` | Excluded (`.gitignore` line 3) | Potential credentials | ✅ Correctly excluded |
| `.env.example` | Tracked (`.gitignore` line 4 `!`) | Placeholder values only | ✅ Safe to track |
| `backend/.env` | Does not exist | N/A | Operator must create |
| `backend/.env.example` | Tracked | Placeholder values | ✅ Safe to track |

**Verified:** `backend/.env.example` contains `<password>` and `<change_to_secure_password>` placeholders — no real credentials. ✅

### 6.3 Credential Separation

**Current state:**

- FastAPI runtime and Alembic migrations share the same `DATABASE_URL` — **INCORRECT**.
- Test isolation guard correctly enforces `oliver_test_user` for Category B — **CORRECT**.
- No production / test credential cross-contamination currently possible (databases don't exist yet).

**Required separation for implementation:**

| Credential Set | Environment Variable | Used By | Must Not Be Used By |
|---|---|---|---|
| Application runtime | `DATABASE_URL` | FastAPI engine | Alembic migrations |
| Alembic migrations | `MIGRATION_DATABASE_URL` | `alembic/env.py` | FastAPI engine at runtime |
| Category B tests | `DATABASE_URL` (set to `oliver_test_user` URL) | `conftest.py` guard | Application runtime DB |

### 6.4 Logging and Exception Handling

**Evidence from `main.py` lines 101–110:**
```python
except OperationalError as e:
    # Do NOT log str(e) — it may contain the connection URL and credentials.
    error_msg = (
        f"FATAL STARTUP BLOCKED: PostgreSQL is unreachable or refused the connection "
        f"({type(e).__name__})..."
    )
    logger.critical(error_msg)
    raise RuntimeError(error_msg) from e
```

`str(e)` is never logged — only `type(e).__name__`. ✅

**Evidence from `health.py` lines 22–25:**
```python
db.execute(text("SELECT 1"))
db_status = "connected"
except Exception as exc:
db_status = f"unhealthy ({type(exc).__name__})"
```

Health check also uses `type(exc).__name__` only — credentials are not exposed. ✅

**Evidence from `conftest.py` lines 193–203:**
```python
except ValueError as _ve:
    print(f"CRITICAL TEST ISOLATION ERROR: {_ve}", file=sys.stderr)
    sys.exit(1)
except Exception:
    print("CRITICAL TEST ISOLATION ERROR: ... malformed ...", file=sys.stderr)
    sys.exit(1)
```

Generic exceptions print only a sanitized message. ✅

**Gap:** `alembic/env.py` uses `engine_from_config()` which may log the connection URL at SQLAlchemy engine log level WARN or above if the connection fails. The `alembic.ini` logger configuration sets `sqlalchemy.engine` to WARN (`handlers =` with no handler). This suppresses engine logging during migrations — acceptable for local development. For production, ensure migration logs are not persisted to files that could be read by unauthorized parties.

### 6.5 Password Storage in Application Code

**Evidence — `auth_service.py` lines 41, 42:**
```python
hashed_password=hash_password(req.password),
```

User passwords are hashed server-side before storage. The raw password never touches the database. ✅

No connection passwords appear in any source file. ✅

---

## 7. Windows + Docker Deployment Compatibility Analysis

### 7.1 Planned Deployment Topology

| Component | Host | Network | Notes |
|---|---|---|---|
| FastAPI (uvicorn) | Windows host (Python) | Host network | Listens on `127.0.0.1:8000` |
| PostgreSQL | Docker container | Docker bridge | Port `5432` forwarded to host |
| Alembic (migration) | Windows host (Python) | Via `localhost:5432` | Runs as `oliver_migrator` |
| Android client | Mobile device | Public internet → FastAPI API only | No DB access |
| `pg_dump` (backup) | Windows host or Docker exec | Via `localhost:5432` or inside container | Stage 2.1A.6 |

### 7.2 Connection URL Matrix

| Role | URL Pattern | Connection Path |
|---|---|---|
| `oliver_app_user` (runtime) | `postgresql+psycopg://oliver_app_user:<pass>@localhost:5432/oliver_db` | Host → Docker port-forward |
| `oliver_migrator` (migration) | `postgresql+psycopg://oliver_migrator:<pass>@localhost:5432/oliver_db` | Host → Docker port-forward |
| `oliver_test_user` (Category B) | `postgresql+psycopg://oliver_test_user:<pass>@127.0.0.1:5432/oliver_test` | Host → Docker port-forward |
| `postgres` (bootstrap/restore) | `postgresql://postgres:<pass>@localhost:5432/postgres` | Host or `docker exec` |

> [!NOTE]
> `localhost` is correct here because FastAPI and Alembic run on the Windows host. When Docker Desktop exposes port 5432, it is reachable as `localhost:5432` from Windows. If FastAPI were ever moved inside a Docker container, the hostname would change to the Compose service name (e.g., `db`).

### 7.3 Role Creation Compatibility

PostgreSQL roles are global to the PostgreSQL instance (not per-database). They must be created once during Docker container initialization. The Docker Compose configuration should use `docker-entrypoint-initdb.d/` SQL scripts that run as the `postgres` superuser on first container creation.

**Windows path concern:** PowerShell is the shell on Windows. All `psql` commands in provisioning scripts must be wrapped for PowerShell execution. Volume paths in Docker Compose must use Linux-style paths inside the container, regardless of Windows host paths.

**`docker-entrypoint-initdb.d/` behavior:** Scripts in this directory run only on the first container start (when the data volume is empty). If the container is rebuilt but the volume is preserved, the scripts do NOT re-run. This is the correct behavior for provisioning — it prevents accidental role recreation.

---

## 8. Threat and Failure Analysis

### T-01: Runtime Credentials Used for Migrations

| Attribute | Value |
|---|---|
| **Description** | `alembic/env.py` currently reads `settings.DATABASE_URL`. If `DATABASE_URL` is set to `oliver_app_user` credentials, Alembic will attempt migrations as the runtime user, which must not have DDL rights. |
| **Severity** | **HIGH** |
| **Impact** | Either migrations fail entirely (if `oliver_app_user` lacks DDL — correct behavior), or if DDL is accidentally granted to `oliver_app_user`, schema changes could be executed by the application runtime. |
| **Mitigation** | Introduce `MIGRATION_DATABASE_URL` env var in `alembic/env.py`. Enforce it in the `run_migrations_offline()` and `run_migrations_online()` functions. Use `oliver_migrator` credentials only for migration. |
| **Fail-closed** | If `oliver_app_user` lacks DDL (as designed), Alembic migrations will fail with a permissions error — the system fails closed. ✅ |

### T-02: Runtime Role Owning Tables

| Attribute | Value |
|---|---|
| **Description** | If `oliver_app_user` creates or owns tables, it implicitly has DROP and ALTER rights on those objects. |
| **Severity** | **HIGH** |
| **Impact** | Application bugs or SQL injection could alter the database schema, truncate tables, or drop indexes. |
| **Mitigation** | Only `oliver_migrator` creates tables. `oliver_app_user` is granted only DML. Grant must use `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO oliver_app_user;` with `ALTER DEFAULT PRIVILEGES` to cover future tables. |
| **Fail-closed** | If `oliver_app_user` has no DDL and attempts a schema change, PostgreSQL raises `ERROR: permission denied for table` or `permission denied for schema`. Application startup does not perform DDL. ✅ |

### T-03: Excessive Database Privileges

| Attribute | Value |
|---|---|
| **Description** | Granting `SUPERUSER`, `CREATEDB`, or `CREATEROLE` to application or test roles. |
| **Severity** | **CRITICAL** |
| **Impact** | A compromised application or test role could create arbitrary users, escalate privileges, or access all databases. |
| **Mitigation** | No role except `postgres` (bootstrap) holds `SUPERUSER`. The `conftest.py` guard explicitly aborts if `oliver_test_user` has superuser privileges (line 353). |
| **Fail-closed** | Category B tests SECURITY ABORT if `is_super` is true. ✅ |

### T-04: Test Credentials Reaching Development Database

| Attribute | Value |
|---|---|
| **Description** | `oliver_test_user` connecting to `oliver_db` instead of `oliver_test`. |
| **Severity** | **HIGH** |
| **Impact** | Test data contaminates the development database; test teardown (`drop_all`) deletes production development data. |
| **Mitigation** | (a) `oliver_test_user` must only be granted CONNECT on `oliver_db` = NO (never grant). (b) `conftest.py` guard enforces that the test database is `oliver_test` (line 125–127). (c) Provisioning scripts must not grant `oliver_test_user` any privileges on `oliver_db`. |
| **Fail-closed** | `conftest.py` will `sys.exit(1)` if `DATABASE_URL` database is not `oliver_test` in Category B mode. ✅ |

### T-05: Test Role Reaching Production

| Attribute | Value |
|---|---|
| **Description** | Mistakenly setting `DATABASE_URL=postgresql+psycopg://oliver_test_user:...@localhost:5432/oliver_db` for the FastAPI application. |
| **Severity** | **HIGH** |
| **Impact** | Application runs against wrong database; `oliver_test_user` may lack required grants on `oliver_db`. |
| **Mitigation** | Role separation by convention: `oliver_test_user` only has privileges on `oliver_test`. Documentation and `.env.example` must make this clear. |
| **Fail-closed** | If `oliver_test_user` has no CONNECT on `oliver_db`, FastAPI startup will fail with `OperationalError` → `RuntimeError`. ✅ |

### T-06: Backup Role With Write Access

| Attribute | Value |
|---|---|
| **Description** | `oliver_backup` being granted INSERT/UPDATE/DELETE. |
| **Severity** | **MEDIUM** |
| **Impact** | A compromised backup process could modify data. |
| **Mitigation** | Grant only CONNECT + SELECT to `oliver_backup`. `pg_dump` requires only SELECT. |
| **Fail-closed** | No DML granted. Any write attempt returns PostgreSQL permission error. ✅ |

### T-07: Admin Credentials Used by FastAPI

| Attribute | Value |
|---|---|
| **Description** | Using the `postgres` superuser password in `DATABASE_URL`. |
| **Severity** | **CRITICAL** |
| **Impact** | Full database superuser access from the application process. Any vulnerability could compromise the entire PostgreSQL instance. |
| **Mitigation** | `DATABASE_URL` must only use `oliver_app_user` credentials. `postgres` credentials must never appear in any application environment file. |
| **Fail-closed** | No automated check prevents this. Operator discipline and clear documentation are the primary mitigations. The `.env.example` template must specify `oliver_app_user` explicitly. |

### T-08: PostgreSQL Unavailable During Startup

| Attribute | Value |
|---|---|
| **Description** | Docker container is not running when FastAPI starts. |
| **Severity** | **MEDIUM** |
| **Impact** | Application fails to start. |
| **Mitigation** | Already handled: `OperationalError` in `_verify_startup_schema()` raises a sanitized `RuntimeError`. Application does not start in a degraded state. |
| **Fail-closed** | `RuntimeError` prevents FastAPI from accepting any requests. ✅ (Stage 2.1A.1 implementation) |

### T-09: DATABASE_URL Pointing to Wrong Database

| Attribute | Value |
|---|---|
| **Description** | `DATABASE_URL` mistakenly set to `oliver_test` or another database. |
| **Severity** | **HIGH** |
| **Impact** | Application reads/writes wrong data; Alembic head check may fail or succeed against wrong schema. |
| **Mitigation** | Provisioning scripts enforce that `oliver_app_user` has CONNECT only on `oliver_db` (not `oliver_test`). If the wrong DB name is supplied and the user has no CONNECT, startup fails. |
| **Fail-closed** | CONNECT privilege restriction causes `OperationalError` → `RuntimeError` at startup. ✅ |

### T-10: Credential Leakage Through Logs, Tracebacks, or Git

| Attribute | Value |
|---|---|
| **Description** | SQLAlchemy connection URLs containing passwords appear in logs or tracebacks. |
| **Severity** | **HIGH** |
| **Impact** | Credentials exposed in log files, CI outputs, or Git history. |
| **Mitigation** | (a) `main.py` never logs `str(e)` for `OperationalError`. (b) `.gitignore` excludes all `.env` and `.env.*` files. (c) `alembic.ini` has no hardcoded URL. (d) Provisioning scripts must not echo passwords. |
| **Fail-closed** | The existing code paths do not log connection strings. ✅ However, `alembic/env.py` does not log sanitization — it passes the URL directly to SQLAlchemy. SQLAlchemy's default engine log at WARN level does not include the password. The `alembic.ini` logger sets `sqlalchemy.engine` to WARN with empty handlers — effectively suppresses engine logs. ✅ |

---

## 9. Stage 2.1A.3 Readiness Requirements

Stage 2.1A.3 is the initial Alembic migration generation. The following prerequisites must be satisfied:

### 9.1 Prerequisites That Stage 2.1A.2 Must Establish

| Requirement | Why Needed | Stage |
|---|---|---|
| `MIGRATION_DATABASE_URL` env var design finalized | `alembic/env.py` must read this instead of `DATABASE_URL` | 2.1A.2 (scope) |
| `oliver_migrator` role and credentials defined | Alembic must connect as `oliver_migrator` | 2.1A.2 (scope) |
| `oliver_db` ownership model documented | Migration must be generated against the correct schema | 2.1A.2 (scope) |
| SQL provisioning scripts ready | Container initialization defines roles/DB before migration | 2.1A.2 (scope) |

### 9.2 What Stage 2.1A.3 Will Create

| Object | Type | Owner | Tables |
|---|---|---|---|
| Initial revision | Alembic script | N/A | N/A |
| `users` table | DDL | `oliver_migrator` | PK, 8 columns |
| `conversations` table | DDL | `oliver_migrator` | PK, 5 columns, FK→users |
| `messages` table | DDL | `oliver_migrator` | PK, 7 columns, FK→conversations+users |
| `refresh_tokens` table | DDL | `oliver_migrator` | PK, 6 columns, FK→users |
| `devices` table | DDL | `oliver_migrator` | PK, 8 columns, FK→users |
| `alembic_version` table | DDL (Alembic managed) | `oliver_migrator` | 1 column |
| Indexes | DDL | `oliver_migrator` | Per SQLAlchemy model `index=True` |

### 9.3 Migration Ordering Requirements (Verified from Models)

The migration must create tables in this order (FK dependency):

```
1. users              (no FK dependencies)
2. conversations      (FK → users.id)
3. refresh_tokens     (FK → users.id)
4. devices            (FK → users.id)
5. messages           (FK → conversations.id AND users.id — dual FK)
```

Alembic autogenerate will detect this ordering from SQLAlchemy's metadata. The generated migration must be reviewed before application to verify FK order.

### 9.4 How Migration Head Verification Will Work

The `_verify_startup_schema()` function (already implemented) handles this:

1. `ScriptDirectory.get_heads()` reads the latest revision from `alembic/versions/`
2. `MigrationContext.get_current_heads()` reads the applied revision from `alembic_version` table (via `oliver_app_user` CONNECT + SELECT)
3. If mismatch → `RuntimeError` → application does not start

This is already correctly implemented. Stage 2.1A.3 only needs to generate the migration file; the verification logic is in place.

---

## 10. Dependencies and Blockers

| Item | Required By | Current State | Blocker? |
|---|---|---|---|
| `MIGRATION_DATABASE_URL` env var | Stage 2.1A.3 Alembic execution | Not defined | ✅ Design blocker — must be specified in 2.1A.2 |
| `alembic/env.py` updated to read `MIGRATION_DATABASE_URL` | Stage 2.1A.3 | Not done | Authorized in 2.1A.2 implementation |
| PostgreSQL roles defined (this report) | Stage 2.1A.3, 2.1A.4 | Done (planning) | ✅ Resolved by this report |
| SQL provisioning scripts | Stage 2.1A.4 Docker startup | Not created | Authorized in 2.1A.2 implementation |
| Docker Desktop installed | Stage 2.1A.4 | Not installed | Hard blocker (operator action) |
| psycopg installed | Stage 2.1A.5 | Not installed | Hard blocker (operator action) |
| `backend/.env` created | Any PostgreSQL startup | Does not exist | Operator action before Stage 2.1A.4 |

---

## 11. Exact Proposed Future Implementation Scope

> **This section is a plan only. No implementation is authorized until separately authorized.**

### 11.1 Files to Create

#### File 1: `backend/scripts/provision_postgres.sql`

A SQL script to be placed in `docker-entrypoint-initdb.d/` inside the Docker container. Runs once on first container creation as `postgres` superuser.

**Proposed content (not yet implemented):**

```sql
-- ============================================================
-- OLIVER 3.0 PostgreSQL Provisioning Script
-- Runs as postgres superuser on first container initialization.
-- DO NOT run manually against a live database.
-- ============================================================

-- -------------------- ROLES --------------------

-- Migration role: owns databases and schema; executes Alembic
CREATE ROLE oliver_migrator
    LOGIN
    PASSWORD '<MIGRATION_PASSWORD_PLACEHOLDER>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE
    CONNECTION LIMIT 2;

-- Runtime application role: DML only on oliver_db
CREATE ROLE oliver_app_user
    LOGIN
    PASSWORD '<APP_PASSWORD_PLACEHOLDER>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE
    CONNECTION LIMIT 20;

-- Test role: DML on oliver_test only
CREATE ROLE oliver_test_user
    LOGIN
    PASSWORD '<TEST_PASSWORD_PLACEHOLDER>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE
    CONNECTION LIMIT 10;

-- Backup role: SELECT only (no login by default for local dev)
CREATE ROLE oliver_backup
    NOLOGIN
    NOSUPERUSER NOCREATEDB NOCREATEROLE
    CONNECTION LIMIT 1;

-- -------------------- PRODUCTION DATABASE --------------------

CREATE DATABASE oliver_db
    OWNER = oliver_migrator
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- -------------------- TEST DATABASE --------------------

CREATE DATABASE oliver_test
    OWNER = oliver_migrator
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- -------------------- PRODUCTION GRANTS --------------------

-- Revoke default public schema access from public role
\c oliver_db
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Runtime app user: CONNECT + schema USAGE + DML
GRANT CONNECT ON DATABASE oliver_db TO oliver_app_user;
GRANT USAGE ON SCHEMA public TO oliver_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO oliver_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;

-- Backup role: CONNECT + schema USAGE + SELECT
GRANT CONNECT ON DATABASE oliver_db TO oliver_backup;
GRANT USAGE ON SCHEMA public TO oliver_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO oliver_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO oliver_backup;

-- -------------------- TEST DATABASE GRANTS --------------------

\c oliver_test

-- Transfer public schema ownership to oliver_test_user
-- (Required by conftest.py line 383)
ALTER SCHEMA public OWNER TO oliver_test_user;

-- Test user: CONNECT + schema ownership (DDL via ownership) + DML
GRANT CONNECT ON DATABASE oliver_test TO oliver_test_user;

-- Migrator needs CONNECT for running migrations in oliver_test
GRANT CONNECT ON DATABASE oliver_test TO oliver_migrator;
```

**Password substitution:** Passwords must NOT be hardcoded in this script. The Docker Compose `environment:` block must inject them via build args or the script must use `\set` with psql variables. The recommended approach: use a wrapper shell script that calls `psql` with `--variable=MIGRATION_PASSWORD=$POSTGRES_MIGRATOR_PASSWORD` etc., reading from Docker Compose environment variables.

#### File 2: `backend/scripts/set_alembic_grants.sql`

Run once after the initial Alembic migration (Stage 2.1A.3b) to ensure `oliver_app_user` has SELECT on `alembic_version`:

```sql
\c oliver_db
GRANT SELECT ON alembic_version TO oliver_app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO oliver_app_user;
```

This is separated from the provisioning script because `alembic_version` does not exist until after the first migration.

#### File 3: `backend/.env.example` (update)

Add the `MIGRATION_DATABASE_URL` variable to the PostgreSQL section:

```
# MIGRATION_DATABASE_URL is used exclusively by Alembic for schema migrations.
# NEVER use this in backend/.env — the application must only use DATABASE_URL.
# MIGRATION_DATABASE_URL="postgresql+psycopg://oliver_migrator:<migration_pass>@localhost:5432/oliver_db"
```

#### File 4: `backend/alembic/env.py` (update)

Add `MIGRATION_DATABASE_URL` support:

```python
import os
from backend.app.core.config import settings

def get_migration_url() -> str:
    """Return the migration URL. Must be oliver_migrator credentials, not app user."""
    migration_url = os.environ.get("MIGRATION_DATABASE_URL")
    if not migration_url:
        raise RuntimeError(
            "MIGRATION_DATABASE_URL is not set. "
            "Alembic requires separate migration credentials (oliver_migrator). "
            "Never use DATABASE_URL for migrations."
        )
    return migration_url

def run_migrations_offline() -> None:
    url = get_migration_url()
    context.configure(url=url, ...)

def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_migration_url()
    ...
```

### 11.2 Files NOT to Create or Modify in Stage 2.1A.2

- `backend/app/main.py` — No changes needed
- `backend/tests/conftest.py` — No changes needed (already encodes all requirements)
- `backend/app/core/database.py` — No changes needed
- `backend/app/core/config.py` — No changes needed (MIGRATION_DATABASE_URL is NOT a Settings field — it's read directly from `os.environ` in `alembic/env.py` to prevent it from ever loading into the application settings)
- Either SQLite database — Absolutely protected

### 11.3 Role Creation Order

```
1. Connect as postgres superuser (via docker exec or psql)
2. CREATE ROLE oliver_migrator
3. CREATE ROLE oliver_app_user
4. CREATE ROLE oliver_test_user
5. CREATE ROLE oliver_backup
6. CREATE DATABASE oliver_db OWNER oliver_migrator
7. CREATE DATABASE oliver_test OWNER oliver_migrator
8. \c oliver_db — configure production grants
9. \c oliver_test — configure test grants
10. ALTER SCHEMA public OWNER TO oliver_test_user (in oliver_test only)
```

### 11.4 Permission Grant Order

Grants must come AFTER role and database creation. Within each database:

```
1. REVOKE from PUBLIC
2. GRANT CONNECT
3. GRANT USAGE ON SCHEMA
4. GRANT table-level DML
5. ALTER DEFAULT PRIVILEGES for future tables
```

---

## 12. Validation and Rollback Strategy

### 12.1 Validation Plan (Post-Implementation)

After provisioning scripts are executed (Stage 2.1A.4):

```sql
-- Verify roles exist
SELECT rolname, rolsuper, rolcreatedb, rolcanlogin, rolconnlimit
FROM pg_roles
WHERE rolname IN ('oliver_migrator','oliver_app_user','oliver_test_user','oliver_backup');

-- Verify database ownership
SELECT datname, r.rolname AS owner
FROM pg_database d JOIN pg_roles r ON d.datdba = r.oid
WHERE datname IN ('oliver_db', 'oliver_test');

-- Verify schema ownership in oliver_test
\c oliver_test
SELECT n.nspname, r.rolname AS owner
FROM pg_namespace n JOIN pg_roles r ON n.nspowner = r.oid
WHERE n.nspname = 'public';

-- Verify app user cannot DDL
SET ROLE oliver_app_user;
CREATE TABLE test_forbidden (id int);  -- Must fail with permission denied
```

After running Category B tests:

```
OLIVER_TEST_MODE=category_b DATABASE_URL=<oliver_test_user URL> pytest backend/tests/
```

The `pytest_sessionstart()` function will independently verify all 7 role-related assertions.

### 12.2 Rollback Plan

**Scenario: Provisioning script fails partway through**

Since this is a fresh Docker volume, the safest rollback is:

```
docker compose down -v   # Removes the volume entirely
docker compose up -d     # Recreates volume and reruns initdb scripts
```

> [!CAUTION]
> `docker compose down -v` deletes the PostgreSQL data volume. This is safe ONLY on a fresh provisioning — before any real application data exists. Never use on a volume containing production data. This is documented explicitly in the rollback plan.

**Scenario: Wrong privileges granted**

```sql
-- Connect as postgres superuser
REVOKE ALL ON DATABASE oliver_db FROM oliver_app_user;
REVOKE ALL ON SCHEMA public FROM oliver_app_user;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM oliver_app_user;
-- Then re-grant correctly
```

**Scenario: Wrong schema owner in oliver_test**

```sql
\c oliver_test
ALTER SCHEMA public OWNER TO oliver_test_user;
```

---

## 13. Risk Classification

| ID | Risk | Severity | Probability | Status |
|---|---|---|---|---|
| R-01 | Runtime user used for migrations (T-01) | HIGH | HIGH (current code) | Mitigated by MIGRATION_DATABASE_URL in Stage 2.1A.2 |
| R-02 | Runtime user owns tables (T-02) | HIGH | LOW (provisioning prevents this) | Mitigated by provisioning script |
| R-03 | Superuser used by application (T-07) | CRITICAL | LOW | Mitigated by documentation and `.env.example` |
| R-04 | Test role reaches production database (T-04/T-05) | HIGH | LOW | Mitigated by CONNECT restriction + conftest guard |
| R-05 | Credential leakage in logs (T-10) | HIGH | LOW | Already mitigated in existing code |
| R-06 | Backup role has write access (T-06) | MEDIUM | LOW | Mitigated by SELECT-only grant |
| R-07 | Docker not installed before Stage 2.1A.4 | HIGH | CONFIRMED | Operator must install Docker Desktop |
| R-08 | Passwords committed to Git | CRITICAL | LOW | Mitigated by .gitignore + placeholder templates |
| R-09 | `alembic_version` SELECT missing for app user | MEDIUM | LOW | Mitigated by `set_alembic_grants.sql` (Stage 2.1A.3b) |
| R-10 | `oliver_test_user` schema ownership not set correctly | HIGH | MEDIUM | Mitigated by explicit `ALTER SCHEMA public OWNER` in script |

---

## 14. Final Verdict

```
===========================================================================
STAGE 2.1A.2 READINESS VERDICT: READY WITH CONDITIONS

CONDITIONS THAT MUST BE SATISFIED IN IMPLEMENTATION:

C-01 (CRITICAL): Introduce MIGRATION_DATABASE_URL in alembic/env.py.
     Alembic must NOT use the application DATABASE_URL.
     The migration role (oliver_migrator) must be separate from the
     runtime role (oliver_app_user).

C-02 (HIGH): The provisioning SQL must set:
     ALTER SCHEMA public OWNER TO oliver_test_user; (in oliver_test only)
     This is a hard requirement enforced by conftest.py line 383.

C-03 (HIGH): oliver_migrator must own both oliver_db and oliver_test.
     This is a hard requirement enforced by conftest.py line 369.

C-04 (MEDIUM): oliver_app_user must have SELECT on alembic_version.
     This table does not exist until after Stage 2.1A.3; a separate
     post-migration grant script is required.

C-05 (MEDIUM): Passwords must never be hardcoded in provisioning scripts.
     Use environment variable substitution via Docker Compose.

STAGE 2.1A.3 AND ALL LATER STAGES REMAIN UNAUTHORIZED.
STAGE 2.1A.2 IMPLEMENTATION REQUIRES SEPARATE EXPLICIT AUTHORIZATION.
===========================================================================
```

---

## 15. Final Verification

```
git status --short  →  (empty — working tree clean)

Files created this audit:   1 (this report)
Files modified this audit:  0
Source files modified:      0
Configuration files modified: 0
Test files modified:        0
Database files modified:    0

database/oliver.db:     192,512 bytes, 07-11-2026 19:38:26 — INTACT
backend/oliver_dev.db:  94,208  bytes, 07-11-2026 18:12:44 — INTACT
```

**STOPPING POINT.** No implementation performed. No files modified except this report. Stage 2.1A.2 implementation and all later stages remain unauthorized.
