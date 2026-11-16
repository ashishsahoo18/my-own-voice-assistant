# OLIVER 3.0 — Phase 2.1 Final Remaining Defects Closure & Engineering Safety Audit

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1_FINAL_REMAINING_DEFECTS_CLOSURE_AUDIT.md`  
**Milestone:** Phase 2.1 — PostgreSQL + Docker Architecture  
**Audit Type:** Strictly Read-Only Final Remaining Defects Closure & Engineering Safety Audit  
**Target Environment:** Windows 10/11, Python 3.13.5 AMD64, Docker Desktop (WSL2), PostgreSQL 16, psycopg 3.x, Alembic  
**Preceding Audit Documents (v1.0 – v8.0):** See evidence inventory in Section 4.

---

## 1. Executive Summary

This audit is an evidence-based examination of the **OLIVER 3.0 Phase 2.1 PostgreSQL + Docker Architecture**. It inspects the actual current repository against six specific defect categories identified in the previous round (F-02, F-03, F-04, F-06, F-07, F-09, F-10), and produces a consolidated verdict for all ten findings (F-01 through F-10).

**Critical finding:** The proposed specifications exist exclusively in audit report documents. None of the proposed implementation artifacts — `01-init-roles.sql`, `backup_postgres.ps1`, `readiness.py`, the revised `conftest.py`, the Docker Compose file, or the `oliver_migrator` grant SQL — exist anywhere in the actual repository. The actual `backend/tests/conftest.py` does not contain the proposed isolation guard. The actual `backend/app/main.py` calls `Base.metadata.create_all(bind=engine)` unconditionally on startup with no database-type guard. No `oliver_migrator` role or schema grant scripts exist on disk.

The audit therefore cannot issue a PASS verdict on any finding that relies solely on proposed specifications that have not been placed into actual project files.

**Final Decision:** **CONDITIONAL PASS — SPECIFIC BLOCKERS REMAIN**

The proposed specifications are technically sound at the planning level. However, they have not been committed to the repository. All runtime behaviors remain unverified. Several structural issues in existing code also require correction before implementation.

---

## 2. Audit Scope & Strict Read-Only Boundary

### 2.1 Authorized Operations
- Read-only inspection of repository source code, scripts, configuration, test suites, and documentation.
- Static analysis of code actually present in the repository versus code specified only in planning reports.
- Creation of exactly one new Markdown report.

### 2.2 Prohibited Operations
- No modifications to any source, test, configuration, environment, or database file.
- No package installations, container operations, or Git mutations.
- All unexecuted procedures are classified **NOT RUNTIME VERIFIED**.

---

## 3. Git & Repository Preservation Preflight

### 3.1 Git State
| Item | Value |
|---|---|
| **Branch** | `main` |
| **HEAD Commit** | `d729aff` (`Create OLIVER_3_PHASE_2_1_FINAL_CRITICAL_DEFECT_CLOSURE_AUDIT.md`) |
| **Modified files** | None |
| **Deleted files** | None |
| **Untracked files** | None |
| **Working tree** | Completely clean |

### 3.2 Database Asset Inventory
| File | Size (bytes) | Last Modified | Status |
|---|---|---|---|
| `database/oliver.db` | 192,512 | 07-11-2026 19:38:26 | Intact, closed, unmodified |
| `backend/oliver_dev.db` | 94,208 | 07-11-2026 18:12:44 | Intact, closed, unmodified |
| WAL / SHM files | — | — | None present on disk |

> Note: `backups/pre_migration_20261012_160156/oliver.db-shm` and `oliver.db-wal` exist within the historical backup directory. These are archived backup artefacts, not live database WAL files. They are not modified.

### 3.3 Runtime Environment
- **Docker CLI:** Not found in system PATH.
- **psycopg library:** Not installed (`ModuleNotFoundError`).
- **PostgreSQL services:** None running.

---

## 4. Files Actually Inspected

| File Path | Exists on Disk | Purpose |
|---|---|---|
| `backend/tests/conftest.py` | **YES** (96 lines) | Actual pytest conftest — missing proposed isolation guard |
| `backend/app/core/database.py` | **YES** (47 lines) | Actual SQLAlchemy engine and session |
| `backend/app/core/config.py` | **YES** (62 lines) | Actual Pydantic settings and DATABASE_URL |
| `backend/app/main.py` | **YES** (96 lines) | Actual FastAPI application entrypoint |
| `scripts/test.ps1` | **YES** (667 bytes, 28-10-2026) | Existing test runner — NOT the backup orchestrator |
| `scripts/backup_postgres.ps1` | **NO** | Does not exist on disk |
| `docker-entrypoint-initdb.d/01-init-roles.sql` | **NO** | Does not exist on disk |
| `docker-compose.yml` | **NO** | Does not exist on disk |
| `backend/app/core/readiness.py` | **NO** | Does not exist on disk |
| `docs/OLIVER_3_PHASE_2_1_FINAL_CRITICAL_DEFECT_CLOSURE_AUDIT.md` | **YES** | Most recent planning report (v8.0) |
| `docs/OLIVER_3_PHASE_2_1_FINAL_ENGINEERING_SAFETY_VERIFICATION_REPORT.md` | **YES** | v7.0 |
| `backend/alembic.ini` | **YES** | Alembic configuration |
| `backend/alembic/versions/` | **YES** (contains only `.gitkeep`) | Zero migrations exist |
| `backups/` | **YES** (3 subdirectories) | SQLite-era backup directories; no PostgreSQL dumps |
| `.gitignore` | **YES** | `backups/` is ignored |

---

## 5. Finding F-02 — Role Provisioning & Secret Handling

### 5.1 Evidence Review
The corrected role provisioning SQL (`SELECT format(...) \gexec` with `\getenv`) exists only in the planning report at:
- `docs/OLIVER_3_PHASE_2_1_FINAL_CRITICAL_DEFECT_CLOSURE_AUDIT.md` lines 95–152.

No file `docker-entrypoint-initdb.d/01-init-roles.sql` exists in the repository. No Docker Compose file exists to specify container environment variables or volume mounts.

### 5.2 Technical Assessment of Proposed Specification

#### Correctly Resolved at Specification Level:
| Issue | Assessment | Basis |
|---|---|---|
| Dollar-quoted `DO $$` psql interpolation failure | **RESOLVED IN SPECIFICATION** | Specification uses `SELECT format(...) \gexec` at top level |
| `format('%L', ...)` injection safety | **RESOLVED IN SPECIFICATION** | Escapes all special chars including `'`, `\`, `$`, `;` |
| `\getenv` environment variable ingestion | **RESOLVED IN SPECIFICATION** | No shell expansion; psql reads from process environment |
| `\set ON_ERROR_STOP on` halt on failure | **RESOLVED IN SPECIFICATION** | First directive in script |
| Credential rotation via `WHERE EXISTS` / `WHERE NOT EXISTS` | **RESOLVED IN SPECIFICATION** | Idempotent dual-branch CREATE/ALTER pattern |

#### Remaining Gaps:
1. **`oliver_migrator` role not provisioned.** The specification references `oliver_migrator` in the five-role model (report v8.0 lines 634–641) but the proposed `01-init-roles.sql` does not provision it. The init script provisions only `oliver_app`, `oliver_test_user`, and `oliver_backup`. `oliver_migrator` is assumed to exist without a creation statement.
2. **No Docker Compose file exists.** Without `docker-compose.yml`, the container environment variables (`OLIVER_APP_PASSWORD`, etc.) have no defined delivery path.
3. **Bash pre-flight validator is specification-only.** The Bash secret-validation script exists only in the planning report, not in `scripts/`.
4. **`\o /dev/null` suppresses stdout, not stderr.** A psql error during credential operations still appears in Docker container logs. This is documented as a residual operational risk in the specification and is correct.

**F-02 Status: `PARTIAL` — Specification technically sound; implementation artifacts absent from repository.**

---

## 6. Finding F-03 — Backup Integrity & Restore Verification

### 6.1 Evidence Review
The proposed backup script exists only in:
- `docs/OLIVER_3_PHASE_2_1_FINAL_CRITICAL_DEFECT_CLOSURE_AUDIT.md` lines 209–321.

No `scripts/backup_postgres.ps1` exists on disk. The actual `scripts/test.ps1` (667 bytes, 28-10-2026) is the pre-existing test runner, unrelated to backup operations.

The existing `backups/` directory contains SQLite-era `.db` files and one `.db-wal` / `.db-shm` pair from an archived historical backup. No PostgreSQL `.dump` artifacts exist.

### 6.2 Technical Assessment of Proposed Specification

#### Correctly Resolved at Specification Level:
| Requirement | Assessment | Report Location |
|---|---|---|
| Allowlist validation of `$ContainerName` and `$Database` | **RESOLVED IN SPECIFICATION** | v8.0 lines 227–228 — regex `^[a-zA-Z0-9_-]+$` |
| `& docker @ArgsList` (argument-safe invocation, no `Invoke-Expression`) | **RESOLVED IN SPECIFICATION** | `Execute-Checked` function, v8.0 lines 231–237 |
| `$LASTEXITCODE` checked after each native command | **RESOLVED IN SPECIFICATION** | Each `Execute-Checked` call; `stat` block line 270 |
| Container file size > 0 verified before copy | **RESOLVED IN SPECIFICATION** | v8.0 lines 268–272 |
| `docker cp` for host transfer (not bind-mount `mv`) | **RESOLVED IN SPECIFICATION** | v8.0 lines 274–276 |
| Host file size compared to container file size | **RESOLVED IN SPECIFICATION** | v8.0 lines 278–282 |
| SHA-256 computed on host artifact | **RESOLVED IN SPECIFICATION** | v8.0 lines 285–286 |
| Host artifact copied BACK to container for restore verification | **RESOLVED IN SPECIFICATION** | v8.0 lines 288–290 |
| `DROP DATABASE IF EXISTS oliver_restore_verify WITH (FORCE)` before create | **RESOLVED IN SPECIFICATION** | v8.0 lines 293–294 |
| `pg_restore --exit-on-error` | **RESOLVED IN SPECIFICATION** | v8.0 line 300 |
| Cleanup in `finally` block | **RESOLVED IN SPECIFICATION** | v8.0 lines 313–320 |

#### Remaining Gaps:
1. **Verification database uses a fixed name, not a unique per-run name.** The name `oliver_restore_verify` is a fixed string. The audit prompt requires either a unique per-run name or a safe ownership token. While the `DROP DATABASE IF EXISTS` guard mitigates most residual risks, a fixed name means two concurrent runs of the script would collide. This is a **PARTIAL** resolution because concurrent execution safety is not demonstrated.
2. **No representative row counts verified.** The restore check verifies that exactly 5 tables exist by name (v8.0 lines 304–308), but does not verify row counts or any data integrity. The specification states "Representative row counts" in the Mermaid diagram but does not implement them in the PowerShell script. `CheckRows` in the diagram has no corresponding code.
3. **SHA-256 is self-verified, not independently compared.** The script computes a checksum and writes it to `${hostDumpPath}.sha256`, but never reads and compares it against an independently obtained expected hash. This confirms the file was written, not that it was transferred without corruption beyond what the size check already confirms. The size check and SHA-256 write are complementary but the SHA-256 is not used in a cross-verification step.
4. **Cleanup `$LASTEXITCODE` handling.** The `finally` block at v8.0 lines 316–317 calls `& docker exec ...` but emits only a `Write-Warning` on non-zero exit, which is not a fail-closed behavior for cleanup failures.
5. **`scripts/backup_postgres.ps1` does not exist.** All above is specification-only.

**F-03 Status: `PARTIAL` — Core architecture sound and resolves prior defects; fixed-name verification target, absent row count checks, and non-fail-closed cleanup remain.**

---

## 7. Finding F-04 — Complete Write Freeze & Recovery Guarantees

### 7.1 Evidence Review
The write-freeze protocol exists only in planning report v8.0, Section 6, lines 332–363. No implementation file encodes it.

### 7.2 Technical Assessment

#### Resolved at Specification Level:
| Requirement | Assessment | Basis |
|---|---|---|
| RPO = 0 requires write freeze | **CORRECTLY STATED** | v8.0 lines 335–343 |
| `REVOKE CONNECT ON DATABASE oliver_db FROM oliver_app` | **SPECIFIED** | v8.0 line 341 |
| `ALTER DATABASE oliver_db WITH CONNECTION LIMIT 0` | **SPECIFIED** | v8.0 line 343 |
| `pg_stat_activity` inspection for active/idle-in-transaction | **SPECIFIED** | v8.0 lines 349–357 |
| `pg_prepared_xacts` inspection | **SPECIFIED** | v8.0 lines 353–357 |
| PostgreSQL sole authority after cutover, no SQLite fallback | **SPECIFIED** | v8.0 lines 359–362 |
| PITR unavailable without WAL archiving | **CORRECTLY STATED** | v8.0 line 327 |

#### Remaining Gaps:
1. **Writer inventory is incomplete.** The proposed writer matrix at v8.0 lines 337–343 lists only 4 writer types. The audit prompt requires 12 distinct writer categories: HTTP requests, background workers, scheduler/reminder processes, desktop or other app processes, direct DB clients, administrative clients, external processes, database superuser connections, prepared transactions, active transactions, idle-in-transaction, and ordinary idle sessions capable of writing. The current specification omits:
   - **Desktop application scheduler / reminder processes** (explicitly present in OLIVER: `database/oliver.db` FTS5 tables include reminder data; no evidence of a scheduler is inspected but the architecture includes it).
   - **Administrative sessions** connecting directly as `postgres`.
   - **External scripts and integrations** (e.g., test runners, development tools).
   - **Ordinary idle sessions** that have an open transaction handle but are not currently executing (distinct from `idle in transaction` state).
2. **`REVOKE CONNECT` leaves existing connections open.** `REVOKE CONNECT ON DATABASE oliver_db FROM oliver_app` prevents new connections but does not terminate existing idle or idle-in-transaction sessions. The specification requires these to be terminated separately via `pg_terminate_backend`. This is documented in `pg_stat_activity` check but the sequencing between `REVOKE CONNECT` and `pg_terminate_backend` is not formally specified.
3. **SQLite `backend/oliver_dev.db` read-only enforcement is documented, not technical.** `backend/app/core/config.py` line 32 defaults `DATABASE_URL` to `sqlite:///{BACKEND_DIR / 'oliver_dev.db'}`. The database file remains writable on the filesystem. No OS-level `attrib +R` or file permissions are applied. The claim that it is "maintained in a read-only state" is a documentation claim, not a technical enforcement.
4. **`Base.metadata.create_all(bind=engine)` in `backend/app/main.py` line 33 is unconditional.** This creates tables on whatever database the engine connects to, including PostgreSQL. This must be gated to SQLite-only connections before PostgreSQL cutover to prevent schema corruption in production. This is a **FAIL** on F-08.

**F-04 Status: `PARTIAL` — Core protocol documented; writer inventory incomplete; SQLite read-only enforcement not technical; RPO = 0 is conditional on enforceable full freeze which is not demonstrated.**

---

## 8. Finding F-06 — Existing & Future Object Permissions

### 8.1 Evidence Review
The grant SQL exists only in planning report v8.0 lines 647–665. No SQL file exists on disk that provisions grants, and no `oliver_migrator` role provisioning exists in `01-init-roles.sql`.

### 8.2 Technical Assessment

#### Correctly Resolved at Specification Level:
| Requirement | Assessment | Basis |
|---|---|---|
| `GRANT USAGE ON SCHEMA public TO oliver_app` | **SPECIFIED** | v8.0 line 652 |
| `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES` to `oliver_app` | **SPECIFIED** | v8.0 line 656 |
| `ALTER DEFAULT PRIVILEGES ... FOR ROLE oliver_migrator` correctly limits scope | **PARTIALLY — see below** | v8.0 lines 660–661 |
| `ALTER DEFAULT PRIVILEGES` does not cover existing objects | **CORRECTLY STATED** | v8.0 lines 644–645 |
| Backup role uses `pg_read_all_data` | **SPECIFIED** | v8.0 line 665 |

#### Remaining Gaps:
1. **`ALTER DEFAULT PRIVILEGES` in v8.0 uses the wrong form.** Lines 660–661 specify:
   ```sql
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app;
   ```
   This omits `FOR ROLE oliver_migrator`. Without `FOR ROLE oliver_migrator`, the default privileges apply only to objects created by the current session role (i.e., whatever role is executing the grant SQL — likely `postgres`). Objects created by Alembic running as `oliver_migrator` would NOT receive these default privileges. The correct form is:
   ```sql
   ALTER DEFAULT PRIVILEGES FOR ROLE oliver_migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO oliver_app;
   ```
   **This is a FAIL — the proposed SQL will not grant privileges on future Alembic-created objects.**
2. **`oliver_migrator` role is not provisioned in `01-init-roles.sql`.** The five-role architecture diagram references `oliver_migrator` but the init script does not create it.
3. **No SQL file exists on disk.** All grants remain in report text only.

**F-06 Status: `FAIL` — `ALTER DEFAULT PRIVILEGES` missing `FOR ROLE oliver_migrator` clause; `oliver_migrator` not provisioned in init script; no implementation files exist.**

---

## 9. Finding F-07 — Authenticated PostgreSQL Readiness & Endpoint Verification

### 9.1 Evidence Review
The proposed `backend/app/core/readiness.py` exists only in the planning report at v8.0 lines 374–511. The file does not exist on disk.

### 9.2 Technical Assessment of Proposed Specification

#### Correctly Resolved at Specification Level:
| Requirement | Assessment | Basis |
|---|---|---|
| Explicit SQL column aliases (`curr_user`, `sess_user`, `curr_db`) | **RESOLVED IN SPECIFICATION** | v8.0 lines 414–421 |
| `current_user` and `session_user` retrieved and compared separately | **RESOLVED IN SPECIFICATION** | v8.0 lines 425–434 |
| `has_database_privilege(current_user, current_database(), 'CONNECT')` | **RESOLVED IN SPECIFICATION** | v8.0 line 420 |
| `datdba` database ownership check | **RESOLVED IN SPECIFICATION** | v8.0 lines 442–448 |
| `pg_database_owner` role membership check | **RESOLVED IN SPECIFICATION** | v8.0 lines 450–453 |
| Schema `USAGE` on `public` | **RESOLVED IN SPECIFICATION** | v8.0 line 462 |
| 20 table privilege permutations (5 tables × 4 ops) | **RESOLVED IN SPECIFICATION** | v8.0 lines 466–478 |
| Dual sequence USAGE + SELECT verification | **RESOLVED IN SPECIFICATION** | v8.0 lines 490–493 |
| No write operations during readiness probe | **RESOLVED IN SPECIFICATION** | v8.0 line 501 |

#### Remaining Gap — CRITICAL:
1. **`expected_host` and `expected_port` parameters are accepted but NOT used.** The function signature at v8.0 line 409 is:
   ```python
   def check_tier2_session(engine: Engine, expected_host: str = "127.0.0.1", expected_port: int = 5432) -> Dict[str, Any]:
   ```
   However, examining lines 411–455, neither `expected_host` nor `expected_port` appears in any comparison. The retrieved `srv_addr` (alias for `inet_server_addr()`) and `srv_port` (alias for `inet_server_port()`) are returned in the dict but are never compared to `expected_host` or `expected_port`. **The endpoint validation parameters are accepted but have no effect.** This directly contradicts the audit requirement and was specifically called out in the audit prompt.
2. **`run_readiness_probe` calls `check_tier2_session(engine)` without passing `expected_host` or `expected_port`.** Even if the internal comparison were added, the caller omits these arguments, using defaults of `127.0.0.1:5432` with no connection to actual engine configuration.
3. **NULL handling for `inet_server_addr()`.** On some PostgreSQL configurations (Unix socket connections), `inet_server_addr()` returns NULL. The specification does not handle or fail-close on a NULL server address, potentially allowing a socket-connected session to bypass endpoint validation.

**F-07 Status: `FAIL` — `expected_host` and `expected_port` parameters accepted but never used in comparisons; NULL server address not handled; file does not exist on disk.**

---

## 10. Finding F-09 — Strict Test-Database Isolation

### 10.1 Evidence Review — Actual `conftest.py` vs Proposed Specification

The actual `backend/tests/conftest.py` (96 lines, committed) contains:
- **Lines 1–19:** Standard imports including `from pathlib import Path`, `import os`, `import sys`.
- **Lines 21–24:** Application module imports AT MODULE LEVEL: `from backend.app.core.database import Base, get_db`, `from backend.app.main import app`.
- **Line 27:** `TEST_DB_URL = "sqlite:///:memory:"` — hardcoded, not env-driven.
- **Lines 29–33:** `test_engine = create_engine(TEST_DB_URL, ...)` — creates engine at module load time.
- **Lines 50–63:** `setup_test_environment` fixture (session-scoped, autouse).
- **Lines 66–71:** `init_test_db` fixture (function-scoped, autouse) — calls `Base.metadata.create_all(bind=test_engine)` and `drop_all` per test.
- **Lines 74–96:** Standard `db_session` and `client` fixtures.

The proposed isolation guard (`enforce_isolation_guard()` called at top of `conftest.py`, `TestIsolationSecurityViolation`, `pytest_sessionstart` hook, `OLIVER_TEST_MODE` enforcement) exists only in planning report v8.0 lines 541–624.

### 10.2 Critical Findings Against Actual Code

| Requirement | Actual Code Status | Assessment |
|---|---|---|
| Isolation guard runs before application imports | `conftest.py` imports `backend.app.core.database` at line 21, before any guard | **FAIL — application module imported at load time before any guard can run** |
| `OLIVER_TEST_MODE` required | No environment variable enforcement exists in actual `conftest.py` | **FAIL — no mode enforcement** |
| Category A: reject `oliver.db` and `oliver_dev.db` | Not enforced; `sqlite:///:memory:` is hardcoded | **NOT VERIFIED — no path check exists** |
| No `assert` for safety guards | Existing code uses `Base.metadata.create_all` without guards | **FAIL — DDL runs unchecked** |
| PostgreSQL isolation guard before DDL | No PostgreSQL guard of any kind | **FAIL — no Category B guard exists** |

### 10.3 Application-Import Side Effect Analysis

When pytest imports `conftest.py`:
1. `backend.app.core.database` is imported at **line 21**.
2. `database.py` **line 10** imports `from backend.app.core.config import settings`.
3. `config.py` **line 61** instantiates `settings = Settings()` at module level.
4. `Settings.__init__` reads `DATABASE_URL` from environment (falls back to `sqlite:///{BACKEND_DIR / 'oliver_dev.db'}`).
5. `database.py` **lines 17–22** immediately call `create_engine(settings.DATABASE_URL, ...)`.
6. `conftest.py` **line 23** imports `from backend.app.main import app`.
7. `main.py` imports `from backend.app.core.database import Base, engine` at **line 15**, which triggers the same chain.

**Result:** By the time any pytest hook or fixture can execute, the production engine referencing `backend/oliver_dev.db` (or whatever `DATABASE_URL` resolves to) has already been created. `pytest_sessionstart` hooks execute after plugin loading but crucially the engine is already instantiated during Python module import, which precedes `pytest_sessionstart`. Any isolation guard in `pytest_sessionstart` is too late to prevent engine creation against the wrong target.

**The proposed fix (top-level `enforce_isolation_guard()` before application imports) is architecturally correct but has not been applied to the actual `conftest.py`.**

**F-09 Status: `FAIL` — Actual `conftest.py` has no isolation guard; application engine is created at import time against production database URL; no `OLIVER_TEST_MODE` enforcement exists.**

---

## 11. Finding F-10 — Backup Role & Backup Capability

### 11.1 Technical Assessment

The proposed grant `GRANT pg_read_all_data TO oliver_backup` (v8.0 line 665) is specified correctly for `pg_dump` logical backup:
- `pg_read_all_data` (PostgreSQL 14+) grants `SELECT` on all tables, views, and sequences in all schemas. This is sufficient for `pg_dump -U oliver_backup`.
- `pg_dump` for a custom-format dump (`-Fc`) requires `SELECT` privilege on all tables and schema traversal permission. `pg_read_all_data` satisfies this.
- `GRANT CONNECT ON DATABASE oliver_db TO oliver_backup` is also specified at v8.0 line 664.

#### Remaining Gaps:
1. **`pg_read_all_data` does not include `pg_restore` permission.** `pg_restore` requires superuser or database ownership to restore ownership and privilege grants from an archive. The script runs `pg_restore -U postgres` for verification (v8.0 line 300), which is correct. The backup role is not used for restores — this is consistent.
2. **No `01-init-roles.sql` file exists on disk** to actually provision `oliver_backup` or grant `pg_read_all_data`.
3. **`--no-owner` flag is not specified in `pg_dump`.** Without `--no-owner`, the dump records ownership. This is correct behavior: the backup should preserve ownership metadata for faithful restore. No defect here.

**F-10 Status: `PARTIAL` — Specification technically correct for `pg_read_all_data` + logical backup; implementation artifacts absent.**

---

## 12. F-01 Through F-10 Final Evidence Matrix

| ID | Previous Defect | Current Evidence | Assessment | Remaining Risk | Required Correction |
|---|---|---|---|---|---|
| **F-01** | Dual-DB boundary not formally specified | Architecture documented in all planning reports; `database/oliver.db` and `backend/oliver_dev.db` are distinct files; no migration logic touches desktop DB | **PASS** (Static) | None at spec level | None |
| **F-02** | Dollar-quoted psql interpolation failure; no `oliver_migrator` provisioned | v8.0 lines 95–167; proposed SQL uses `SELECT format() \gexec` correctly; `01-init-roles.sql` does NOT exist on disk; `oliver_migrator` not in init script | **PARTIAL** | Missing `oliver_migrator` provisioning; no implementation files | Add `oliver_migrator` to init script; create actual `01-init-roles.sql` |
| **F-03** | Restore from container temp not host artifact; no row counts; cleanup suppressed errors | v8.0 lines 207–321; host-artifact copy-back for verification is specified; row counts NOT implemented despite diagram; `oliver_restore_verify` is a fixed name | **PARTIAL** | Fixed verify DB name (concurrent collision); no row count verification; SHA-256 not independently compared; `scripts/backup_postgres.ps1` absent | Use timestamped verify DB name; add row count checks; create actual script |
| **F-04** | Write freeze protocol incomplete | v8.0 lines 332–362; fencing specified; writer inventory misses 8/12 required categories; SQLite not technically read-only; `Base.metadata.create_all` unconditional | **PARTIAL** | Writer inventory incomplete; SQLite technical read-only enforcement absent | Complete writer inventory; add OS-level SQLite protection; gate `create_all` to SQLite only |
| **F-05** | Desktop SQLite boundary not enforced | `database/oliver.db` and `backend/oliver_dev.db` exist as separate files; no migration logic found in codebase touching either | **PASS** (Static) | No technical read-only enforcement on `oliver_dev.db` | Document and enforce read-only status technically |
| **F-06** | `ALTER DEFAULT PRIVILEGES` missing `FOR ROLE oliver_migrator`; no implementation | v8.0 lines 647–665; `FOR ROLE oliver_migrator` ABSENT from SQL; `oliver_migrator` not provisioned anywhere | **FAIL** | Future Alembic-created objects will NOT receive `oliver_app` grants | Correct SQL to include `FOR ROLE oliver_migrator`; provision `oliver_migrator` |
| **F-07** | `expected_host` and `expected_port` accepted but unused; NULL server addr not handled | v8.0 lines 374–511; function signature declares parameters but no comparison exists in body; `backend/app/core/readiness.py` absent | **FAIL** | Endpoint validation is a no-op; NULL server address passes silently | Add `if srv_addr != expected_host` and `if srv_port != expected_port` checks; handle NULL |
| **F-08** | `Base.metadata.create_all(bind=engine)` unconditional in `main.py` lifespan | `backend/app/main.py` line 33: `Base.metadata.create_all(bind=engine)` has no database-type guard | **FAIL** | Will execute DDL against PostgreSQL on startup, corrupting production schema management | Gate to `if settings.DATABASE_URL.startswith("sqlite")` |
| **F-09** | No isolation guard in actual `conftest.py`; engine created at import time | Actual `conftest.py` lines 21–33: application imports and engine creation at module level before any guard can execute; no `OLIVER_TEST_MODE` or guard of any kind | **FAIL** | Existing code runs against production `oliver_dev.db` URL; no PostgreSQL test isolation exists | Apply proposed `conftest.py` changes; run guard before application imports |
| **F-10** | Backup role privilege scope | v8.0 lines 663–665; `pg_read_all_data` + `CONNECT` is correct for logical backup; `pg_restore` uses `postgres`; no `01-init-roles.sql` on disk | **PARTIAL** | Implementation artifacts absent | Create actual grant script |

---

## 13. Architecture & Data-Preservation Assessment

| Architectural Requirement | Status | Evidence |
|---|---|---|
| CustomTkinter desktop application preserved | **CONFIRMED** | No desktop UI files modified |
| Desktop SQLite (`database/oliver.db`) remains local and offline | **CONFIRMED** | File unmodified; no migration references it |
| Desktop FTS5 unaffected | **CONFIRMED** | Zero references to desktop DB in migration planning |
| Backend PostgreSQL as planned shared database | **PLANNED** | No Docker or PostgreSQL files exist yet |
| Original `backend/oliver_dev.db` preserved as cold fallback | **CONFIRMED** | File unmodified (94,208 bytes) |
| No automatic SQLite/PostgreSQL synchronization | **CONFIRMED IN DESIGN** | No sync code present |
| No automatic fallback after PostgreSQL cutover | **CONFIRMED IN DESIGN** | Explicitly prohibited in planning docs |
| REST API contract unchanged by DB migration | **CONFIRMED** | No router or API signature modifications |

---

## 14. Static Versus Runtime Verification Limitations

| Verification Area | Static Status | Runtime Status |
|---|---|---|
| SQL `\gexec` / `\getenv` correctness | Statically verified in specification | **NOT RUNTIME VERIFIED** (no container) |
| Backup script execution and artifact integrity | Statically verified in specification | **NOT RUNTIME VERIFIED** (no script on disk, no container) |
| Readiness probe execution | Statically verified in specification | **NOT RUNTIME VERIFIED** (file absent, no container) |
| Test isolation guard ordering | Static defect confirmed: application imports precede any guard in actual `conftest.py` | **NOT RUNTIME VERIFIED** (not safe to run as-is) |
| PostgreSQL privilege grant execution | Specified only in planning docs | **NOT RUNTIME VERIFIED** |
| RTO measurement | Planning estimate (8–15 min) | **NOT RUNTIME VERIFIED** |
| RPO = 0 enforcement | Protocol documented; writer inventory incomplete | **NOT RUNTIME VERIFIED** |

---

## 15. Remaining Blockers

### CRITICAL BLOCKERS (Must be resolved before Stage 2.1A)
1. **F-07 FAIL: `expected_host` and `expected_port` parameters are accepted but never compared.** Server endpoint validation is a no-op in the proposed `readiness.py`.
2. **F-09 FAIL: Actual `conftest.py` has no isolation guard.** Application engine is instantiated at module import time, before any pytest hook can intervene.
3. **F-08 FAIL: `Base.metadata.create_all(bind=engine)` in `main.py` line 33 is unconditional.** This will create/update tables on PostgreSQL on FastAPI startup, circumventing Alembic schema management.
4. **F-06 FAIL: `ALTER DEFAULT PRIVILEGES` omits `FOR ROLE oliver_migrator`.** Future Alembic-created objects will not receive `oliver_app` grants automatically.
5. **No implementation files exist.** Zero actual infrastructure files (`docker-compose.yml`, `01-init-roles.sql`, `backup_postgres.ps1`, `readiness.py`) are present in the repository.

### HIGH-PRIORITY CONDITIONS
6. **F-02: `oliver_migrator` not provisioned** in proposed `01-init-roles.sql`.
7. **F-03: Fixed verification database name** (`oliver_restore_verify`) risks concurrent execution collisions; row count verification absent; SHA-256 not cross-validated.
8. **F-04: Writer inventory incomplete** (8 of 12 required categories missing).
9. **Docker Desktop not installed; `psycopg` not installed.**

---

## 16. Final Readiness Decision

```
================================================================================
FINAL DECISION: CONDITIONAL PASS — SPECIFIC BLOCKERS REMAIN
================================================================================
```

**Justification:**
The planning and specification work across nine iteration cycles has produced a technically rigorous architectural blueprint. The core design decisions (role separation, `\gexec` substitution, three-tier readiness, fail-closed backup flow, `pytest_sessionstart` ordering concept) are sound.

However, four critical implementation defects remain in the planning specifications (F-06, F-07, F-08, F-09) and zero implementation artifacts have been committed to the repository. The existing application code (`main.py`, `conftest.py`) contains defects that must be corrected before PostgreSQL cutover.

This audit **cannot** issue `PASS — READY FOR IMPLEMENTATION PLANNING` because:
- F-06 contains a SQL defect (`FOR ROLE oliver_migrator` missing).
- F-07 contains a code defect (endpoint parameters unused).
- F-08 contains an existing code defect (unconditional `create_all`).
- F-09: the actual `conftest.py` has no isolation guard.

---

## 17. Recommended Next Actions

**The following are recommendations only. No implementation is authorized by this report.**

1. **Correct F-06:** Add `FOR ROLE oliver_migrator` to both `ALTER DEFAULT PRIVILEGES` statements.
2. **Correct F-07:** Add endpoint comparison logic to `check_tier2_session` and handle NULL `inet_server_addr()`.
3. **Correct F-08:** Gate `Base.metadata.create_all(bind=engine)` in `main.py` to `if settings.DATABASE_URL.startswith("sqlite")`.
4. **Correct F-09:** Apply the proposed `conftest.py` guard architecture to the actual file.
5. **Add `oliver_migrator`** provisioning to `01-init-roles.sql`.
6. **Use a timestamped verification database name** in `backup_postgres.ps1`.
7. **Add row count verification** to restore check.
8. **Create infrastructure files:** `docker-compose.yml`, `01-init-roles.sql`, `scripts/backup_postgres.ps1`, `backend/app/core/readiness.py`.
9. **Request explicit user authorization** for a corrected implementation planning session before Stage 2.1A begins.

---

## 18. Explicit Authorization Boundary

> **MANDATORY NOTICE:**  
> This report is a **strictly read-only audit and defect identification document**.  
> **IT DOES NOT AUTHORIZE IMPLEMENTATION OF ANY CORRECTION.**  
>
> No files may be created, modified, or deleted. No packages may be installed. No containers may be started. No databases may be modified.  
>
> Await explicit user authorization before beginning any implementation, correction, or environment setup.

---

## 19. Post-Audit Git-State Comparison

### Pre-Audit State
- HEAD: `d729aff`
- Modified: 0 files
- Untracked: 0 files

### Post-Audit State
- Exactly ONE new file created: `docs/OLIVER_3_PHASE_2_1_FINAL_REMAINING_DEFECTS_CLOSURE_AUDIT.md`
- Source code modified: **0 files**
- Test files modified: **0 files**
- Configuration, environment, or database files modified: **0 files**
- Git mutations: **0**

```
================================================================================
END OF FINAL REMAINING DEFECTS CLOSURE & ENGINEERING SAFETY AUDIT
================================================================================
```
