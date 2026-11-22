# OLIVER 3.0 — Stage 2.1A.2 SEC-07–SEC-10 Final Security Closure Audit

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A2_SEC07_10_FINAL_SECURITY_CLOSURE_AUDIT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Migration  
**Stage:** 2.1A.2 — PostgreSQL Roles & Permissions (Security Closure)  
**Audit Date:** 2026-11-22  
**Audit Mode:** STRICTLY READ-ONLY — Zero source modifications, zero database mutations  
**Target Reference:** `docs/OLIVER_3_PHASE_2_1A2_POSTGRESQL_ROLES_PERMISSIONS_SECURITY_CORRECTION_AUDIT.md`  
**Baseline Git Commit:** `f24b231` ("Create OLIVER_3_PHASE_2_1A1_IMPLEMENTATION_REPORT.md")

---

## 1. Executive Summary

This report performs the final technical and security closure audit for OLIVER 3.0 Stage 2.1A.2 (PostgreSQL Roles & Permissions). It resolves the remaining security concerns designated **SEC-07 through SEC-10**, re-evaluates **SEC-01 through SEC-06**, and establishes an implementation-ready, fail-closed specification for the role provisioning architecture.

### Key Audit Findings & Resolutions

1. **SEC-07 (Password Handling & Injection Prevention):** The previously proposed heredoc shell interpolation (`PASSWORD '${POSTGRES_MIGRATOR_PASSWORD}'`) is **VULNERABLE** to shell expansion, syntax breaks, and SQL injection if passwords contain single quotes (`'`), backslashes (`\`), or dollar signs (`$`). Furthermore, unset environment variables create accounts with blank passwords, and shell tracing (`set -x`) exposes secrets in container logs.  
   *Resolution:* Enforce bash validation (`set +x`, mandatory minimum 16-character length), quote the heredoc delimiter (`<<- 'EOSQL'`) to disable shell expansion, pass environment variables via `psql -v var="$ENV"`, and use psql's native literal quoting (`:'var'`) which automatically escapes SQL strings.

2. **SEC-08 (Backup Role Least Privilege):** The proposed `oliver_backup` role with `pg_read_all_data` is **OVERLY PERMISSIVE**. In PostgreSQL 14+, `pg_read_all_data` is a cluster-wide super-reader that grants read access across all schemas in all databases, violating isolation between `oliver_db` and `oliver_test`. Furthermore, backup execution is not part of Stage 2.1A.2.  
   *Resolution:* **DEFER** the `oliver_backup` role entirely to Stage 2.1A.6 (Backup & Recovery). For local Docker development, backups will execute via container boundary (`docker exec`). This narrows Stage 2.1A.2 to exactly three non-superuser roles (`oliver_migrator`, `oliver_app_user`, `oliver_test_user`).

3. **SEC-09 (Alembic Version Table Permission Isolation):** The blanket `ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator ... GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user` inadvertently grants write access to `alembic_version` once created by Alembic. The application runtime (`_verify_startup_schema()`) requires **SELECT ONLY**. Write access to `alembic_version` introduces risk of migration state tampering via application compromise.  
   *Resolution:* In Stage 2.1A.3 (Initial Migration), the post-migration step must explicitly execute `REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE alembic_version FROM oliver_app_user;` and confirm only `GRANT SELECT` remains.

4. **SEC-10 (Docker Initialization & Persistent Volume Safety):** `/docker-entrypoint-initdb.d/` scripts run **only once** on an empty volume. If container restarts occur or if a script is manually re-run, unhandled `CREATE ROLE` or `CREATE DATABASE` statements throw errors. Furthermore, destructive commands such as `docker compose down -v` must be explicitly prohibited.  
   *Resolution:* Make `init_postgres.sh` idempotent using `DO $$ BEGIN ... END $$` role existence checks and database existence queries. Formally prohibit volume deletion in all operational runbooks.

**Final Audit Verdict:** **READY FOR STAGE 2.1A.2 IMPLEMENTATION (WITH SPECIFIED CLOSURE CORRECTIONS)**

---

## 2. Mandatory Safety Restrictions & Verification

### 2.1 Execution Scope
- Strictly read-only static analysis and code verification.
- Inspection of `backend/app/core/config.py`, `backend/app/core/database.py`, `backend/app/main.py`, `backend/alembic/env.py`, `backend/tests/conftest.py`, and `backend/.env.example`.
- No files created or modified except this single report.
- SQLite databases remained unopened and unmodified.

### 2.2 Git Baseline Verification
- **Branch:** `main`
- **HEAD Commit:** `f24b231`
- **Working Tree:** Exactly 2 untracked audit documents from previous turns; zero modified tracked files.

### 2.3 Database Integrity
- `database/oliver.db`: 192,512 bytes, Last Modified 07-11-2026 19:38:26 — **INTACT**
- `backend/oliver_dev.db`: 94,208 bytes, Last Modified 07-11-2026 18:12:44 — **INTACT**

---

## 3. Detailed Investigation of SEC-07 through SEC-10

### 3.1 SEC-07 — Password Handling & SQL Injection Prevention
- **Classification:** **FAIL (IN PREVIOUS PROPOSED DESIGN) — CORRECTED BELOW**
- **Repository Evidence:**
  The previously proposed initialization script `backend/scripts/init_postgres.sh` (Section 11 of the Security Correction Audit) contained:
  ```bash
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
      CREATE ROLE oliver_migrator WITH LOGIN PASSWORD '${POSTGRES_MIGRATOR_PASSWORD}' ...;
  EOSQL
  ```
- **Technical Vulnerabilities:**
  1. *Unquoted Heredoc Shell Expansion:* Because `EOSQL` is unquoted, the shell expands `${POSTGRES_MIGRATOR_PASSWORD}` prior to passing the text to `psql`.
  2. *SQL Injection via Special Characters:* If a password contains a single quote (`'`), e.g., `O'Reilly#2026`, the SQL command string evaluates to:
     `CREATE ROLE oliver_migrator WITH LOGIN PASSWORD 'O'Reilly#2026' ...;`
     This causes an immediate SQL syntax failure or allows arbitrary SQL execution if characters like `'; DROP DATABASE ...` are present.
  3. *Backslash and Dollar Sign Escaping:* Backslashes (`\`) trigger psql client meta-command evaluation or SQL escape string interpretation. Dollar signs (`$`) trigger secondary shell parameter expansion.
  4. *Unset or Empty Variables:* If `POSTGRES_MIGRATOR_PASSWORD` is unset in the environment, the command executes `PASSWORD ''`, creating a role with an empty password.
  5. *Credential Leakage via Shell Tracing:* If the container environment or script has `set -x` enabled, the fully expanded heredoc with plaintext passwords prints to `stderr`, becoming permanently captured in Docker container logs (`docker logs oliver_postgres`).
- **Required Implementation Specification:**
  The corrected script must:
  - Disable shell tracing immediately: `set +x`.
  - Validate that all required password variables are present, non-empty, and meet a minimum length (>= 16 characters).
  - Use a **quoted heredoc delimiter** (`<<- 'EOSQL'`), which instructs bash to treat the heredoc body as a literal string with zero variable expansion.
  - Pass secrets into `psql` via `-v varname="$ENV_VAR"`.
  - Reference passwords in SQL via psql's literal substitution syntax: `:'varname'`. Psql automatically escapes single quotes, backslashes, and special characters per SQL standard.

---

### 3.2 SEC-08 — Backup Role Least Privilege
- **Classification:** **FAIL (IN PREVIOUS PROPOSED DESIGN) — RESOLVED BY DEFERRAL**
- **Evaluation:**
  1. *Excessive Scope of `pg_read_all_data`:* The previous proposal suggested `GRANT pg_read_all_data TO oliver_backup;`. PostgreSQL documentation states:
     > `pg_read_all_data`: Read all data (tables, views, sequences), as if having SELECT rights on those objects, and USAGE rights on all schemas, even without explicit grants.
     This grant is **cluster-wide**. It allows `oliver_backup` to read data from `oliver_test`, the `postgres` system catalog, and any future database hosted on the cluster. This directly violates the isolation requirement between production and test databases.
  2. *Timing and Milestone Alignment:* Stage 2.1A.2 is scoped strictly to "PostgreSQL Roles & Permissions" for the backend application and test isolation. Backup and recovery procedures are explicitly scheduled for **Stage 2.1A.6** ("Backup & Recovery").
  3. *Local Development Realities:* In local Docker development, logical backups (`pg_dump`) are executed directly via `docker exec -t oliver_postgres pg_dump -U postgres oliver_db`, which relies on local container administration rather than a dedicated network-exposed database role.
- **Resolution:**
  **DEFER** the `oliver_backup` role to Stage 2.1A.6.
  - Omit `oliver_backup` from `backend/scripts/init_postgres.sh`.
  - The cluster role count in Stage 2.1A.2 is reduced to exactly three non-superuser roles:
    1. `oliver_migrator` (DDL & migration owner)
    2. `oliver_app_user` (FastAPI DML)
    3. `oliver_test_user` (Category B pytest runner)
  - This removes cluster-wide privilege risks and eliminates unused attack surface.

---

### 3.3 SEC-09 — Alembic Version Table Permission Isolation
- **Classification:** **FAIL (IN PREVIOUS PROPOSED DESIGN) — CORRECTED BELOW**
- **Repository Evidence:**
  In `backend/app/main.py:98-100`:
  ```python
  with engine.connect() as conn:
      context = MigrationContext.configure(conn)
      current_heads = context.get_current_heads()
  ```
  `MigrationContext.get_current_heads()` executes:
  `SELECT version_num FROM alembic_version;`
- **Technical Vulnerability:**
  The proposed default privileges in `oliver_db`:
  ```sql
  ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;
  ```
  When `oliver_migrator` runs the initial Alembic migration (`alembic upgrade head`), Alembic creates the table `alembic_version`. Under this default privilege rule, `oliver_app_user` automatically receives `SELECT, INSERT, UPDATE, DELETE` on `alembic_version`.
- **Impact:**
  Write access to `alembic_version` by the runtime application violates least privilege. A compromised web application or SQL injection vulnerability could allow an attacker to alter or delete `alembic_version`, blinding `_verify_startup_schema()` or causing corrupt schema state during subsequent migrations.
- **Required Implementation Specification:**
  In Stage 2.1A.3 (Initial Alembic Migration), immediately after `alembic upgrade head` creates the schema, execute a post-migration grant script:
  ```sql
  -- Restrict alembic_version to read-only for application runtime
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE alembic_version FROM oliver_app_user;
  GRANT SELECT ON TABLE alembic_version TO oliver_app_user;
  ```
  This guarantees `oliver_app_user` has read-only access to verify migration status without permission to mutate the migration ledger.

---

### 3.4 SEC-10 — PostgreSQL Docker Initialization & Existing Volume Safety
- **Classification:** **PASS WITH CONDITIONS**
- **Evaluation:**
  1. *Single-Execution Constraint:* Docker's official `/docker-entrypoint-initdb.d/` executes `.sh` and `.sql` scripts **strictly when the data directory (`PGDATA`) is empty**. On subsequent container restarts with an existing volume, initialization scripts do not re-run.
  2. *Idempotency Requirement:* If `init_postgres.sh` is manually invoked against an existing cluster (e.g. for configuration audit or repair), standard `CREATE ROLE` and `CREATE DATABASE` statements throw fatal errors.
  3. *Destructive Commands Prohibited:* Earlier documentation colloquially suggested `docker compose down -v` to reset state. In a persistent or production environment, `down -v` irrevocably destroys all database data and persistent volumes.
- **Required Implementation Specification:**
  1. Structure `init_postgres.sh` to check for role and database existence before creation:
     ```sql
     DO $$
     BEGIN
         IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oliver_migrator') THEN
             CREATE ROLE oliver_migrator WITH LOGIN PASSWORD :'migrator_pw' ...;
         END IF;
     END
     $$;
     ```
  2. Query `pg_database` in bash before attempting `CREATE DATABASE`:
     ```bash
     if ! psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tc "SELECT 1 FROM pg_database WHERE datname = 'oliver_db'" | grep -q 1; then
         psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE oliver_db WITH OWNER = oliver_migrator ENCODING = 'UTF8';"
     fi
     ```
  3. Formally prohibit `docker compose down -v` and manual volume deletion in all documentation and runbooks.

---

## 4. Revalidation of Previous Security Corrections (SEC-01–SEC-06)

| ID | Issue | Previous Status | Current Audit Revalidation | Verdict |
|---|---|---|---|---|
| **SEC-01** | `CONNECT` not revoked from `PUBLIC` | Identified | Verified: `REVOKE CONNECT, TEMPORARY ON DATABASE ... FROM PUBLIC;` must be executed for both `oliver_db` and `oliver_test`. Explicit `GRANT CONNECT` given only to authorized roles. | **PASS** |
| **SEC-02** | Default privileges without `FOR ROLE` | Identified | Verified: `ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public ...` correctly applies DML grants on future tables created by migrations. | **PASS** |
| **SEC-03** | Missing `public` schema ownership in `oliver_db` | Identified | Verified: `ALTER SCHEMA public OWNER TO oliver_migrator;` inside `oliver_db` ensures Alembic can create objects in PostgreSQL 15+. | **PASS** |
| **SEC-04** | `MIGRATION_DATABASE_URL` invisible to `os.environ` | Identified | Verified: `backend/alembic/env.py` must use `dotenv_values()` from `python-dotenv` (confirmed installed) to read `backend/.env` directly. Fails closed if unset. | **PASS** |
| **SEC-05** | Backup role design flaws | Identified | Resolved: Role deferred entirely to Stage 2.1A.6. No cluster-wide `pg_read_all_data` granted in Stage 2.1A.2. | **PASS** |
| **SEC-06** | Static SQL credential placeholders | Identified | Resolved: Plaintext SQL replaced with shell script using quoted heredoc (`<<- 'EOSQL'`) and psql literal parameterization (`:'migrator_pw'`). | **PASS** |

---

## 5. Verified Role & Database Isolation Matrix

| Role | Production DB (`oliver_db`) | Test DB (`oliver_test`) | Schema Ownership | DDL Rights | DML Rights | Special Restrictions |
|---|---|---|---|---|---|---|
| `postgres` | Full Superuser | Full Superuser | Cluster Admin | Cluster Admin | Cluster Admin | Bootstrap & Docker init only. Never used by app or Alembic. |
| `oliver_migrator` | `CONNECT`, Owner | `CONNECT`, Owner | `oliver_db.public` | Full in `oliver_db` | Full in `oliver_db` | Non-superuser (`NOSUPERUSER NOCREATEDB NOCREATEROLE`). Connection limit 2. |
| `oliver_app_user` | `CONNECT`, `USAGE` on schema | **NO ACCESS** (`REVOKE CONNECT`) | **NONE** | **NONE** (Zero DDL) | `SELECT, INSERT, UPDATE, DELETE` on app tables; `SELECT` on `alembic_version` | Non-superuser. Connection limit 20. Cannot access `oliver_test`. Cannot DDL. |
| `oliver_test_user` | **NO ACCESS** (`REVOKE CONNECT`) | `CONNECT`, Owner of `public` | `oliver_test.public` | Full in `oliver_test.public` | Full in `oliver_test.public` | Non-superuser, not `pg_database_owner`. Connection limit 10. Cannot access `oliver_db`. |
| `oliver_backup` | **DEFERRED** | **DEFERRED** | **DEFERRED** | **DEFERRED** | **DEFERRED** | Deferred to Stage 2.1A.6. |

---

## 6. Complete Implementation-Ready Initialization Script Design

The exact specification for `backend/scripts/init_postgres.sh`:

```bash
#!/usr/bin/env bash
# ==============================================================================
# OLIVER 3.0 — PostgreSQL Cluster Initialization Script
# Executed by official PostgreSQL Docker container on first volume initialization.
# Conforms to Stage 2.1A.2 SEC-01 through SEC-10 security closure specifications.
# ==============================================================================

set -eo pipefail
set +x # Strictly prevent secret exposure in shell traces

# ------------------------------------------------------------------------------
# 1. Environment Variable Validation
# ------------------------------------------------------------------------------
for var in POSTGRES_MIGRATOR_PASSWORD POSTGRES_APP_PASSWORD POSTGRES_TEST_PASSWORD; do
    val="${!var}"
    if [ -z "$val" ]; then
        echo "FATAL INIT ERROR: Required environment variable $var is unset or empty." >&2
        exit 1
    fi
    if [ "${#val}" -lt 16 ]; then
        echo "FATAL INIT ERROR: $var must be at least 16 characters for security." >&2
        exit 1
    fi
done

echo "OLIVER 3.0: Initializing PostgreSQL roles and databases with strict least privilege..."

# ------------------------------------------------------------------------------
# 2. Role Creation (Idempotent, Safe Parameterization via psql variables)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v migrator_pw="$POSTGRES_MIGRATOR_PASSWORD" \
     -v app_pw="$POSTGRES_APP_PASSWORD" \
     -v test_pw="$POSTGRES_TEST_PASSWORD" <<- 'EOSQL'
    -- Migration role: owns databases and schema; executes Alembic
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oliver_migrator') THEN
            CREATE ROLE oliver_migrator WITH LOGIN PASSWORD :'migrator_pw'
                NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 2;
        END IF;
    END
    $$;

    -- Runtime application role: DML only on oliver_db
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oliver_app_user') THEN
            CREATE ROLE oliver_app_user WITH LOGIN PASSWORD :'app_pw'
                NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 20;
        END IF;
    END
    $$;

    -- Test role: DDL and DML on oliver_test only
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oliver_test_user') THEN
            CREATE ROLE oliver_test_user WITH LOGIN PASSWORD :'test_pw'
                NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 10;
        END IF;
    END
    $$;
EOSQL

# ------------------------------------------------------------------------------
# 3. Database Creation (Idempotent)
# ------------------------------------------------------------------------------
for dbname in oliver_db oliver_test; do
    if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -tc "SELECT 1 FROM pg_database WHERE datname = '$dbname'" | grep -q 1; then
        echo "Creating database: $dbname (Owner: oliver_migrator)..."
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
             -c "CREATE DATABASE $dbname WITH OWNER = oliver_migrator ENCODING = 'UTF8';"
    fi
done

# ------------------------------------------------------------------------------
# 4. Connection Isolation (SEC-01: Revoke PUBLIC CONNECT)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<- 'EOSQL'
    -- Sever default PUBLIC connection rights
    REVOKE CONNECT, TEMPORARY ON DATABASE oliver_db FROM PUBLIC;
    REVOKE CONNECT, TEMPORARY ON DATABASE oliver_test FROM PUBLIC;

    -- Grant explicitly to authorized identities
    GRANT CONNECT ON DATABASE oliver_db TO oliver_migrator, oliver_app_user;
    GRANT CONNECT ON DATABASE oliver_test TO oliver_migrator, oliver_test_user;
EOSQL

# ------------------------------------------------------------------------------
# 5. Production Database Schema & Default Privileges (oliver_db)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "oliver_db" <<- 'EOSQL'
    -- Assign public schema ownership to oliver_migrator (SEC-03)
    ALTER SCHEMA public OWNER TO oliver_migrator;
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO oliver_migrator;
    GRANT USAGE ON SCHEMA public TO oliver_app_user;

    -- Configure default privileges for future objects created by oliver_migrator (SEC-02)
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app_user;
    ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO oliver_app_user;
EOSQL

# ------------------------------------------------------------------------------
# 6. Test Database Schema (oliver_test — Satisfies conftest.py:383)
# ------------------------------------------------------------------------------
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "oliver_test" <<- 'EOSQL'
    -- Transfer public schema ownership to oliver_test_user
    ALTER SCHEMA public OWNER TO oliver_test_user;
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO oliver_test_user;
    GRANT ALL PRIVILEGES ON SCHEMA public TO oliver_test_user;
EOSQL

echo "OLIVER 3.0: PostgreSQL provisioning completed successfully."
```

---

## 7. Findings Classification Summary

| Concern | Area | Result | Classification |
|---|---|---|---|
| **SEC-01** | PUBLIC Database Access | `REVOKE CONNECT ... FROM PUBLIC` mandatory | **PASS** (Specification verified) |
| **SEC-02** | Default Privileges | Explicit `FOR ROLE oliver_migrator` mandatory | **PASS** (Specification verified) |
| **SEC-03** | Schema Ownership | `ALTER SCHEMA public OWNER TO oliver_migrator;` | **PASS** (Specification verified) |
| **SEC-04** | Migration Config | `dotenv_values()` in `backend/alembic/env.py` | **PASS** (Specification verified) |
| **SEC-05** | Backup Role Least Privilege | Backup role deferred to Stage 2.1A.6 | **DEFERRED** |
| **SEC-06** | Secret Handling | Quoted heredoc + psql `-v` literal parameterization | **PASS** (Specification verified) |
| **SEC-07** | Injection Prevention | Bash validation + `set +x` + psql `:'var'` | **PASS** (Design corrected) |
| **SEC-08** | Backup Scope | Removed `pg_read_all_data`, deferred to 2.1A.6 | **DEFERRED** |
| **SEC-09** | Alembic Table Isolation | Post-migration `REVOKE` on `alembic_version` | **PASS** (Specification verified) |
| **SEC-10** | Volume Lifecycle | Idempotent queries + prohibit `down -v` | **PASS** (Specification verified) |

---

## 8. Final Verdict & Authorization Status

```
===========================================================================
STAGE 2.1A.2 FINAL SECURITY CLOSURE VERDICT:
READY FOR STAGE 2.1A.2 IMPLEMENTATION (WITH SPECIFIED CLOSURE CORRECTIONS)

All security concerns (SEC-01 through SEC-10) have been rigorously audited,
defects in earlier drafts corrected, and verified against actual repository
code and test fixtures.

AUTHORIZED FILES FOR IMPLEMENTATION (WHEN USER AUTHORIZATION IS GIVEN):
1. backend/scripts/init_postgres.sh (NEW)
2. backend/alembic/env.py (MODIFIED — dotenv credential loading)
3. backend/.env.example (MODIFIED — migration & container env templates)
4. docs/OLIVER_3_PHASE_2_1A2_IMPLEMENTATION_REPORT.md (NEW)

CURRENT STATUS:
STRICTLY READ-ONLY. Implementation is NOT yet authorized.
Awaiting explicit user authorization before creating or modifying any files.
===========================================================================
```
