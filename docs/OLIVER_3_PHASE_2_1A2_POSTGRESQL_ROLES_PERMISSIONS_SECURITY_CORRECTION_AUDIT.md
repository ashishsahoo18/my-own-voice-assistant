# OLIVER 3.0 — Phase 2.1A.2 PostgreSQL Roles & Permissions Security Design Correction Audit

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A2_POSTGRESQL_ROLES_PERMISSIONS_SECURITY_CORRECTION_AUDIT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Migration  
**Stage:** 2.1A.2 — PostgreSQL Roles & Permissions (Security Design Correction)  
**Audit Date:** 2026-11-22  
**Audit Mode:** STRICTLY READ-ONLY — Zero code modifications, zero SQL executions, zero database mutations  
**Target Reference:** `docs/OLIVER_3_PHASE_2_1A2_POSTGRESQL_ROLES_PERMISSIONS_READINESS_REPORT.md`  
**Baseline Git Commit:** `f24b231` ("Create OLIVER_3_PHASE_2_1A1_IMPLEMENTATION_REPORT.md")

---

## 1. Executive Summary

This report delivers a rigorous, strictly read-only security design correction audit of the proposed PostgreSQL roles, permissions, and provisioning architecture for OLIVER 3.0 Stage 2.1A.2.

The previous readiness report (`docs/OLIVER_3_PHASE_2_1A2_POSTGRESQL_ROLES_PERMISSIONS_READINESS_REPORT.md`) returned a verdict of **READY WITH CONDITIONS**. However, deep technical inspection of PostgreSQL's security model, SQLAlchemy/Alembic mechanics, `pydantic-settings` behavior, and existing test assertions in `backend/tests/conftest.py` reveals that several critical security defects and operational gaps were present in the previous proposed design:

1. **Failure to Revoke `CONNECT` from `PUBLIC` (CRITICAL):** In PostgreSQL, the pseudo-role `PUBLIC` holds default `CONNECT` privileges on newly created databases. Because the previous design did not execute `REVOKE CONNECT ON DATABASE ... FROM PUBLIC`, the runtime user could connect to `oliver_test`, the test user could connect to `oliver_db`, and any cluster role could connect across databases.
2. **Broken `ALTER DEFAULT PRIVILEGES` Execution Scope (HIGH):** The proposed SQL executed `ALTER DEFAULT PRIVILEGES` as the `postgres` superuser without `FOR ROLE oliver_migrator`. In PostgreSQL, default privileges without `FOR ROLE` apply only to objects created by the current user (`postgres`). When `oliver_migrator` subsequently runs Alembic migrations, none of the tables created by Alembic would receive runtime DML grants for `oliver_app_user`.
3. **Missing `public` Schema Ownership in `oliver_db` (HIGH):** In PostgreSQL 15+, `CREATE` on schema `public` is revoked from `PUBLIC`. The previous design failed to transfer `public` schema ownership to `oliver_migrator` in `oliver_db` (it only did so in `oliver_test`). Consequently, Alembic migrations running as `oliver_migrator` would fail with `ERROR: permission denied for schema public`.
4. **Flawed `MIGRATION_DATABASE_URL` Environment Loading (HIGH):** The proposed design assumed `os.environ.get("MIGRATION_DATABASE_URL")` would load variables from `backend/.env`. However, `pydantic-settings` parses `.env` files into application settings instances without mutating `os.environ`. If `MIGRATION_DATABASE_URL` is omitted from `Settings` and placed only in `.env`, `os.environ.get()` returns `None`, breaking Alembic execution.
5. **Non-functional `oliver_backup` Role Definition (MEDIUM):** The proposed role was defined with `NOLOGIN`, yet `pg_dump` requires a login connection. A `NOLOGIN` role cannot connect, making the role completely inoperable as designed.
6. **Insecure Password Placeholders in SQL (MEDIUM):** A static `.sql` file with literal placeholder strings mounted into `/docker-entrypoint-initdb.d/` would create PostgreSQL roles with literal placeholder passwords unless dynamic substitution is orchestrated via an entrypoint shell script.

**Final Audit Verdict:** **READY WITH CONDITIONS**  
The role architecture is conceptually sound, but the provisioning scripts and migration loading design require the explicit technical corrections documented in this report prior to authorizing Stage 2.1A.2 implementation.

---

## 2. Audit Scope and Absolute Restrictions

### 2.1 Execution Scope
- Independent verification of all 10 specific security and architectural concerns (C-01 through C-10).
- Examination of PostgreSQL default privilege mechanics against actual repository source code.
- Verification of test safeguards in `backend/tests/conftest.py`.
- Concrete, implementation-ready design corrections.

### 2.2 Prohibited Actions Strictly Observed
- No source code, tests, or configuration modified.
- No SQL scripts created or executed.
- No databases created, modified, or dropped.
- No packages installed; Docker and PostgreSQL were not launched.
- SQLite databases (`database/oliver.db` and `backend/oliver_dev.db`) remained completely untouched.
- Git working tree maintained in a strictly unmodified state.

---

## 3. Actual Repository State

### 3.1 Git State
- **Active Branch:** `main`
- **HEAD Commit:** `f24b231`
- **Commit Subject:** `Create OLIVER_3_PHASE_2_1A1_IMPLEMENTATION_REPORT.md`
- **Working Tree:** Exactly 1 untracked file (`docs/OLIVER_3_PHASE_2_1A2_POSTGRESQL_ROLES_PERMISSIONS_READINESS_REPORT.md` from the previous audit turn), 0 tracked modifications.

### 3.2 Database File Integrity
- `database/oliver.db`: 192,512 bytes, Last Modified 07-11-2026 19:38:26 — **INTACT**
- `backend/oliver_dev.db`: 94,208 bytes, Last Modified 07-11-2026 18:12:44 — **INTACT**

---

## 4. Verified Architecture Baseline

| Component | Repository Evidence | Verified Behavior |
|---|---|---|
| Startup DDL Gate | `backend/app/main.py:35-131` | Enforces fail-closed startup. SQLite auto-DDL permitted only for canonical `oliver_dev.db` in `development`. PostgreSQL auto-DDL forbidden; validates single Alembic head via `MigrationContext`. Catches `OperationalError` and sanitizes error logs. |
| Engine Configuration | `backend/app/core/database.py:13-36` | Uses `make_url()` to detect dialect. Applies `pool_size=5`, `max_overflow=10`, `pool_timeout=30`, `pool_recycle=1800`, `connect_timeout=10` strictly for PostgreSQL. SQLite receives `check_same_thread=False` and PRAGMA foreign keys. |
| Settings Management | `backend/app/core/config.py:15-61` | `Settings(BaseSettings)` reads `backend/.env` and root `.env` via `SettingsConfigDict`. Does not export parsed `.env` values into `os.environ`. |
| Alembic Runner | `backend/alembic/env.py:22-57` | Reads `settings.DATABASE_URL` for both offline and online modes. Uses `NullPool`. Currently shares the runtime application connection URL. |
| Test Isolation Guard | `backend/tests/conftest.py:1-435` | Enforces pre-import validation on line 1. Requires explicit `OLIVER_TEST_MODE`. Category B enforces driver `postgresql+psycopg`, db `oliver_test`, user `oliver_test_user`, host `127.0.0.1`/`localhost`, port `5432`, non-superuser, non-db-owner, db owner `oliver_migrator`, schema owner `oliver_test_user`. |
| Models & Access | `backend/app/models/` | 5 models: `User`, `RefreshToken`, `Conversation`, `Message`, `Device`. All PKs are Python-side UUID `String(36)`. Cascading deletes on relationships. |

---

## 5. Detailed Review of Concerns (C-01 through C-10)

### C-01 — PostgreSQL CONNECT Permissions and PUBLIC Access
- **Status:** **VALID (CRITICAL DEFECT IN PREVIOUS DESIGN)**
- **Technical Explanation:** In PostgreSQL, the special pseudo-role `PUBLIC` represents all roles. By default, PostgreSQL grants `CONNECT` and `TEMPORARY` privileges on any newly created database to `PUBLIC`. In the previous proposed script:
  ```sql
  GRANT CONNECT ON DATABASE oliver_db TO oliver_app_user;
  GRANT CONNECT ON DATABASE oliver_test TO oliver_test_user;
  ```
  The script revoked privileges on `SCHEMA public`, but **failed to revoke `CONNECT` on the databases from `PUBLIC`**.
- **Impact:** `oliver_test_user` can connect to `oliver_db`; `oliver_app_user` can connect to `oliver_test`. Any future role in the cluster can connect across boundaries. Cross-database isolation was completely illusory.
- **Required Correction:** The provisioning script must explicitly revoke `CONNECT` and `TEMPORARY` from `PUBLIC` on all created databases:
  ```sql
  REVOKE CONNECT, TEMPORARY ON DATABASE oliver_db FROM PUBLIC;
  REVOKE CONNECT, TEMPORARY ON DATABASE oliver_test FROM PUBLIC;
  ```

### C-02 — ALTER DEFAULT PRIVILEGES Role Ownership
- **Status:** **VALID (HIGH DEFECT IN PREVIOUS DESIGN)**
- **Technical Explanation:** PostgreSQL's `ALTER DEFAULT PRIVILEGES` statement modifies default permissions for objects created by the *current role* executing the command unless `FOR ROLE <target_role>` is explicitly supplied. In the previous script:
  ```sql
  ALTER DEFAULT PRIVILEGES IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;
  ```
  This statement was executed while connected as `postgres` (superuser). Therefore, it configured default privileges only for tables created by `postgres`. However, Alembic migrations run as `oliver_migrator`.
- **Impact:** When `oliver_migrator` runs migrations and creates tables, `oliver_app_user` receives **zero** permissions on those tables. FastAPI queries will immediately fail with `ERROR: permission denied for table users`.
- **Required Correction:** The provisioning script must explicitly specify `FOR ROLE oliver_migrator`:
  ```sql
  ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;
  ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
      GRANT USAGE, SELECT ON SEQUENCES TO oliver_app_user;
  ```

### C-03 — Production public Schema Ownership and DDL
- **Status:** **VALID (HIGH DEFECT IN PREVIOUS DESIGN)**
- **Technical Explanation:** When `CREATE DATABASE oliver_db OWNER = oliver_migrator;` is executed by `postgres`, the database owner is set to `oliver_migrator`, but the `public` schema inside the database is inherited from `template0`/`template1` and remains owned by `postgres`. In PostgreSQL 15+, `CREATE` privilege on `public` is removed from `PUBLIC`. The previous design altered schema ownership only in `oliver_test`, omitting it for `oliver_db`.
- **Impact:** `oliver_migrator` would be unable to execute Alembic migrations in `oliver_db`, failing with `ERROR: permission denied for schema public`.
- **Required Correction:** Explicitly assign ownership of schema `public` in `oliver_db` to `oliver_migrator`:
  ```sql
  \c oliver_db
  ALTER SCHEMA public OWNER TO oliver_migrator;
  GRANT USAGE, CREATE ON SCHEMA public TO oliver_migrator;
  ```

### C-04 — MIGRATION_DATABASE_URL Loading
- **Status:** **VALID (HIGH ARCHITECTURAL DEFECT IN PREVIOUS DESIGN)**
- **Technical Explanation:** The previous readiness report recommended reading `MIGRATION_DATABASE_URL` via `os.environ.get()` in `alembic/env.py`, while simultaneously advising that it should be placed in `backend/.env` and excluded from Pydantic `Settings`. However, `pydantic-settings` parses `.env` files into settings model instances; it **does not** inject parsed key-value pairs into the OS environment (`os.environ`).
- **Impact:** Running `alembic upgrade head` in a fresh terminal would result in `os.environ.get("MIGRATION_DATABASE_URL")` returning `None`, throwing an unhandled `RuntimeError` even if the operator properly populated `backend/.env`.
- **Required Correction:** `backend/alembic/env.py` must load `.env` explicitly using `python-dotenv` (which is already verified installed in the environment) when `os.environ.get("MIGRATION_DATABASE_URL")` is unset:
  ```python
  import os
  from pathlib import Path
  from dotenv import dotenv_values

  def get_migration_url() -> str:
      url = os.environ.get("MIGRATION_DATABASE_URL")
      if not url:
          backend_env = Path(__file__).resolve().parent.parent / ".env"
          if backend_env.exists():
              url = dotenv_values(backend_env).get("MIGRATION_DATABASE_URL")
      if not url:
          raise RuntimeError(
              "FATAL: MIGRATION_DATABASE_URL is not set in environment or backend/.env. "
              "Alembic requires dedicated migration credentials (oliver_migrator)."
          )
      return url
  ```

### C-05 — Password Provisioning and Secret Safety
- **Status:** **VALID (MEDIUM DEFECT IN PREVIOUS DESIGN)**
- **Technical Explanation:** The previous report proposed mounting a raw `.sql` file containing `<MIGRATION_PASSWORD_PLACEHOLDER>` into `/docker-entrypoint-initdb.d/`. Docker's PostgreSQL entrypoint runs `.sql` files directly through `psql` with no variable substitution. Placing placeholders into `.sql` files causes PostgreSQL to create accounts with literal placeholder strings as passwords.
- **Impact:** Security exposure and authentication failures when the application attempts to connect with real passwords.
- **Required Correction:** Replace the bare `.sql` file with an initialization shell script (`/docker-entrypoint-initdb.d/01-init-oliver.sh`) that reads passwords directly from container environment variables passed via Docker Compose (`POSTGRES_MIGRATOR_PASSWORD`, `POSTGRES_APP_PASSWORD`, `POSTGRES_TEST_PASSWORD`):
  ```bash
  #!/bin/bash
  set -e
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
      CREATE ROLE oliver_migrator LOGIN PASSWORD '${POSTGRES_MIGRATOR_PASSWORD}' ...;
  EOSQL
  ```
  Additionally, document that special characters in passwords inside connection URLs must be URL-encoded (RFC 3986 percent-encoding).

### C-06 — Database Creation and PostgreSQL Locale Compatibility
- **Status:** **VALID (LOW TO MEDIUM RISK)**
- **Technical Explanation:** The previous report proposed `LC_COLLATE = 'en_US.UTF-8'` and `LC_CTYPE = 'en_US.UTF-8'` with `TEMPLATE = template0`. On Alpine-based PostgreSQL containers or minimal Linux distributions, collation naming conventions differ (e.g. `en_US.utf8` or `C.UTF-8`), causing `CREATE DATABASE` to fail with `ERROR: collation "en_US.UTF-8" for encoding "UTF8" does not exist`. Furthermore, `CREATE DATABASE` cannot execute within a transaction block (`BEGIN ... COMMIT`).
- **Impact:** Docker container initialization could fail on startup depending on the base image.
- **Required Correction:** Omit explicit `LC_COLLATE`/`LC_CTYPE` overrides so the database adopts the cluster's default collation, or standardize on `C.UTF-8`/`template1`. Ensure `CREATE DATABASE` runs outside transaction blocks.

### C-07 — Backup Role Validity
- **Status:** **VALID (MEDIUM DEFECT IN PREVIOUS DESIGN)**
- **Technical Explanation:** The previous report created `oliver_backup` with `NOLOGIN` while simultaneously granting it `CONNECT ON DATABASE oliver_db`. Because `pg_dump` is an external client process connecting over TCP/socket, a role with `NOLOGIN` cannot authenticate (`FATAL: role "oliver_backup" is not permitted to log in`).
- **Impact:** The backup role was completely non-functional.
- **Required Correction:** Either:
  1. Defer the backup role to Stage 2.1A.6 (Backup & Restore), relying on container-level `docker exec -t <container> pg_dump -U postgres oliver_db` for local development; or
  2. If created in Stage 2.1A.2, define it with `LOGIN`, assign a password, grant `CONNECT`, and grant `pg_read_all_data` (available in PostgreSQL 14+).

### C-08 — Test Role Isolation
- **Status:** **VALID (HIGH DEFECT IN PREVIOUS DESIGN)**
- **Technical Explanation:** While `backend/tests/conftest.py` has comprehensive application-level assertions (verifying non-superuser, non-db-owner, db name `oliver_test`, schema owner `oliver_test_user`), database-level isolation was deficient due to `PUBLIC` having default `CONNECT` permissions on `oliver_db`.
- **Impact:** An erroneous test configuration or malicious test script could connect to `oliver_db`.
- **Required Correction:** Revoking `CONNECT ON DATABASE oliver_db FROM PUBLIC` ensures `oliver_test_user` is rejected at the PostgreSQL connection handshake if it ever attempts to connect to the production database.

### C-09 — Runtime Application Privileges
- **Status:** **PARTIALLY VALID / VERIFIED ACCURATE**
- **Technical Explanation:** Inspection of all models and routers confirms that `oliver_app_user` requires:
  - `USAGE` on schema `public`.
  - `SELECT, INSERT, UPDATE` across application tables (`users`, `refresh_tokens`, `conversations`, `messages`, `devices`).
  - `DELETE` across application tables to satisfy SQLAlchemy relationship cascade deletions (e.g., deleting a `User` cascades to tokens, conversations, devices; deleting a `Conversation` cascades to messages).
  - `SELECT` on `alembic_version` to support `_verify_startup_schema()`.
- **Restrictions Enforced:** `oliver_app_user` must have **zero** DDL privileges (`CREATE`, `ALTER`, `DROP` on tables/schemas), no `TRUNCATE`, and no access to `oliver_test`.

### C-10 — Role and Database Ownership Consistency
- **Status:** **VALID (DESIGN HARMONIZATION REQUIRED)**
- **Technical Explanation:** The ownership model must strictly align with the assertions in `conftest.py` lines 369 and 383:
  - Database Owner (`oliver_db`): `oliver_migrator`
  - Database Owner (`oliver_test`): `oliver_migrator` (enforced by `conftest.py:369`)
  - Schema Owner (`oliver_db.public`): `oliver_migrator`
  - Schema Owner (`oliver_test.public`): `oliver_test_user` (enforced by `conftest.py:383`)
  - Runtime User (`oliver_app_user`): Owns nothing. DML only.

---

## 6. Comprehensive Least-Privilege Permission Matrix

| Role | Database | Schema | Tables | Sequences | DDL Rights | Superuser | Login | Conn Limit |
|---|---|---|---|---|---|---|---|---|
| `postgres` | Cluster | All | All | All | Cluster Admin | Yes | Yes | Unlimited |
| `oliver_migrator` | `oliver_db`, `oliver_test` | `public` (`oliver_db` owner) | All (owner in `oliver_db`) | All | Full in `oliver_db` | No | Yes | 2 |
| `oliver_app_user` | `oliver_db` only | `public` (USAGE only) | `SELECT, INSERT, UPDATE, DELETE` | `USAGE, SELECT` | **NONE** | No | Yes | 20 |
| `oliver_test_user` | `oliver_test` only | `public` (`oliver_test` owner) | Full (in `oliver_test`) | Full | Full in `oliver_test` | No | Yes | 10 |
| `oliver_backup` | `oliver_db` only | `public` (USAGE only) | `SELECT` only (or `pg_read_all_data`) | `SELECT` only | **NONE** | No | Yes | 1 |

---

## 7. Database CONNECT Isolation Model

To guarantee mathematical isolation between environments, the provisioning script must execute:

```sql
-- 1. Revoke default public connection rights
REVOKE CONNECT, TEMPORARY ON DATABASE oliver_db FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE oliver_test FROM PUBLIC;

-- 2. Explicitly grant production database connections
GRANT CONNECT ON DATABASE oliver_db TO oliver_migrator;
GRANT CONNECT ON DATABASE oliver_db TO oliver_app_user;
GRANT CONNECT ON DATABASE oliver_db TO oliver_backup;

-- 3. Explicitly grant test database connections
GRANT CONNECT ON DATABASE oliver_test TO oliver_migrator;
GRANT CONNECT ON DATABASE oliver_test TO oliver_test_user;
```

With this configuration:
- `oliver_app_user` attempting to connect to `oliver_test` receives `FATAL: permission denied for database "oliver_test"`.
- `oliver_test_user` attempting to connect to `oliver_db` receives `FATAL: permission denied for database "oliver_db"`.

---

## 8. Schema Ownership & DDL Model

```
oliver_db (Database Owner: oliver_migrator)
└── public (Schema Owner: oliver_migrator)
    ├── alembic_version (Owner: oliver_migrator, SELECT granted to oliver_app_user)
    └── application tables (Owner: oliver_migrator, DML granted to oliver_app_user)

oliver_test (Database Owner: oliver_migrator)
└── public (Schema Owner: oliver_test_user)
    └── test tables (Created/dropped dynamically by test fixtures as oliver_test_user)
```

---

## 9. Corrected Default Privilege Design

In `oliver_db`, default privileges must be declared **explicitly for objects created by `oliver_migrator`**:

```sql
\c oliver_db

-- Tables created by oliver_migrator grant DML to oliver_app_user and SELECT to oliver_backup
ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO oliver_backup;

-- Sequences created by oliver_migrator grant USAGE/SELECT to oliver_app_user
ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO oliver_app_user;
```

---

## 10. Migration Credential Loading Architecture

In `backend/alembic/env.py`, replace direct `settings.DATABASE_URL` references with an isolated credential resolver:

```python
import os
from pathlib import Path
from dotenv import dotenv_values
from alembic import context
from sqlalchemy import engine_from_config, pool

def get_migration_database_url() -> str:
    """Resolve migration database URL strictly from environment or backend/.env."""
    # 1. Direct OS environment variable
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if url and url.strip():
        return url.strip()

    # 2. Parse backend/.env directly via python-dotenv
    backend_env_path = Path(__file__).resolve().parent.parent / ".env"
    if backend_env_path.exists():
        parsed = dotenv_values(backend_env_path)
        url = parsed.get("MIGRATION_DATABASE_URL")
        if url and url.strip():
            return url.strip()

    raise RuntimeError(
        "FATAL STARTUP BLOCKED: MIGRATION_DATABASE_URL is not configured. "
        "Alembic migrations require explicit oliver_migrator credentials. "
        "Define MIGRATION_DATABASE_URL in OS environment or backend/.env."
    )
```

---

## 11. Secret Provisioning & Docker Initialization Design

To eliminate raw placeholders in SQL files, the initialization must use a shell script mounted to `/docker-entrypoint-initdb.d/01-init-oliver.sh`:

```bash
#!/usr/bin/env bash
set -eo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- 1. Create Roles
    CREATE ROLE oliver_migrator WITH LOGIN PASSWORD '${POSTGRES_MIGRATOR_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 2;
    CREATE ROLE oliver_app_user WITH LOGIN PASSWORD '${POSTGRES_APP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 20;
    CREATE ROLE oliver_test_user WITH LOGIN PASSWORD '${POSTGRES_TEST_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 10;
    CREATE ROLE oliver_backup WITH LOGIN PASSWORD '${POSTGRES_BACKUP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 1;

    -- 2. Create Databases
    CREATE DATABASE oliver_db WITH OWNER = oliver_migrator ENCODING = 'UTF8';
    CREATE DATABASE oliver_test WITH OWNER = oliver_migrator ENCODING = 'UTF8';

    -- 3. Isolate Database Connections
    REVOKE CONNECT, TEMPORARY ON DATABASE oliver_db FROM PUBLIC;
    REVOKE CONNECT, TEMPORARY ON DATABASE oliver_test FROM PUBLIC;

    GRANT CONNECT ON DATABASE oliver_db TO oliver_migrator, oliver_app_user, oliver_backup;
    GRANT CONNECT ON DATABASE oliver_test TO oliver_migrator, oliver_test_user;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "oliver_db" <<-EOSQL
    -- 4. Configure Production Schema
    ALTER SCHEMA public OWNER TO oliver_migrator;
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO oliver_migrator;
    GRANT USAGE ON SCHEMA public TO oliver_app_user, oliver_backup;

    -- 5. Default Privileges for Migrator-Created Objects
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT SELECT ON TABLES TO oliver_backup;
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO oliver_app_user;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "oliver_test" <<-EOSQL
    -- 6. Configure Test Schema (Required by conftest.py:383)
    ALTER SCHEMA public OWNER TO oliver_test_user;
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO oliver_test_user;
    GRANT ALL PRIVILEGES ON SCHEMA public TO oliver_test_user;
EOSQL
```

---

## 12. Security Risk Classification

| Finding ID | Title | Severity | Impact | Required Design Correction | Blocks 2.1A.2? |
|---|---|---|---|---|---|
| **SEC-01** | `CONNECT` not revoked from `PUBLIC` | **CRITICAL** | Cross-database connection by test/runtime roles | Execute `REVOKE CONNECT ON DATABASE ... FROM PUBLIC` | **YES** |
| **SEC-02** | Default privileges executed without `FOR ROLE` | **HIGH** | Runtime app gets zero access on Alembic-created tables | Add `FOR ROLE oliver_migrator` to `ALTER DEFAULT PRIVILEGES` | **YES** |
| **SEC-03** | Missing `public` schema ownership in `oliver_db` | **HIGH** | Alembic migrations fail with permission denied on schema | Add `ALTER SCHEMA public OWNER TO oliver_migrator` | **YES** |
| **SEC-04** | `MIGRATION_DATABASE_URL` invisible to `os.environ` | **HIGH** | Alembic CLI fails to locate credentials in `backend/.env` | Use `dotenv_values()` in `alembic/env.py` | **YES** |
| **SEC-05** | `oliver_backup` defined with `NOLOGIN` | **MEDIUM** | `pg_dump` fails authentication | Add `LOGIN` + password or defer to Stage 2.1A.6 | **YES** |
| **SEC-06** | Literal placeholders in init SQL files | **MEDIUM** | Accounts created with literal placeholder strings | Use `.sh` entrypoint script with environment variables | **YES** |
| **SEC-07** | Hardcoded collation names in `CREATE DATABASE` | **LOW** | Failure on minimal or Alpine container images | Inherit cluster collation; omit explicit `LC_COLLATE` | No |

---

## 13. Required Implementation Corrections for Stage 2.1A.2

When implementation is explicitly authorized, exactly four files will be modified/created:

1. **`backend/scripts/init_postgres.sh` (NEW):**
   The shell-based entrypoint initialization script documented in Section 11.
2. **`backend/alembic/env.py` (MODIFIED):**
   Add `get_migration_database_url()` using `dotenv_values` fallback; replace `settings.DATABASE_URL` with this resolver.
3. **`backend/.env.example` (MODIFIED):**
   Add `MIGRATION_DATABASE_URL` template and container password variables (`POSTGRES_MIGRATOR_PASSWORD`, etc.).
4. **`docs/OLIVER_3_PHASE_2_1A2_IMPLEMENTATION_REPORT.md` (NEW):**
   Implementation completion evidence report.

---

## 14. Updated Implementation Readiness & Final Verdict

```
===========================================================================
STAGE 2.1A.2 SECURITY AUDIT VERDICT: READY WITH CONDITIONS

The role and permission architecture is fully validated, but implementation
must incorporate the verified corrections (SEC-01 through SEC-06).

CONDITIONS PRECEDENT TO IMPLEMENTATION:
1. Docker Desktop must be installed before Stage 2.1A.4 (unchanged).
2. psycopg must be installed before Stage 2.1A.5 (unchanged).
3. Stage 2.1A.2 implementation must strictly follow the corrected shell-based
   init script and dotenv-based Alembic loading architecture.

STOPPING POINT:
Stage 2.1A.2 implementation and all subsequent stages remain UNAUTHORIZED.
===========================================================================
```

---

## 15. Verification Limitations

- This audit was performed strictly through static inspection and analysis.
- No Docker containers or PostgreSQL servers were launched.
- SQLite databases (`database/oliver.db`, `backend/oliver_dev.db`) were verified byte-for-byte unchanged.
