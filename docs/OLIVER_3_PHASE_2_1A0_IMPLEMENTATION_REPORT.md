# OLIVER 3.0 — Stage 2.1A.0 Implementation Report: Startup Schema Safety & Test Database Isolation

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A0_IMPLEMENTATION_REPORT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Migration  
**Stage:** 2.1A.0 — Startup Safety and Test Isolation  
**Implementation Date:** 2026-11-20  
**Implementation Mode:** Minimal, safety-first, evidence-based  
**Approved Baseline Commit:** `87f7230` (Branch `main`, HEAD before implementation `f7bebc9`)  
**Execution Boundary:** STRICTLY STAGE 2.1A.0 ONLY. Exactly two authorized source files modified. Zero package installations, zero container execution, zero database operations.

---

## 1. Implementation Summary

Stage 2.1A.0 has been successfully implemented in exact accordance with the authoritative engineering specification in `docs/OLIVER_3_PHASE_2_1A0_FINAL_CODE_LEVEL_DEFECT_CLOSURE_AUDIT.md`.

This stage hardens the OLIVER 3.0 central backend against accidental database modifications, unsafe schema mutations, and test harness database cross-contamination:
1. **Startup Schema Safety (`backend/app/main.py`):** Replaces raw, unconditional `Base.metadata.create_all()` with a deterministic, fail-closed `_verify_startup_schema()` function. Automatic DDL is strictly restricted to development SQLite against the authorized canonical database `backend/oliver_dev.db` (or `:memory:`). Startup against PostgreSQL requires verified Alembic migrations and strictly forbids `create_all()`.
2. **Pre-Import Test Isolation Guard (`backend/tests/conftest.py`):** Implements a Line 1 pre-import URL validation guard that parses `DATABASE_URL` before application or database modules load, rejects unauthorized targets, enforces explicit test-mode matching (`category_a` vs `category_b`), hardens against Windows Win32 path normalization bypasses, and performs secondary engine URL parity and live PostgreSQL identity assertions in `pytest_sessionstart()`.

---

## 2. Exact Files Changed

Exactly two source files were modified. No other repository files were altered.

| File Path | Nature of Modification | Lines Added | Lines Deleted | Status |
|---|---|---|---|---|
| `backend/app/main.py` | Added deterministic path resolution, Alembic migration verification, and `_verify_startup_schema()`; preserved all routers, middleware, and endpoints. | 113 | 4 | **MODIFIED (Verified)** |
| `backend/tests/conftest.py` | Added Line 1 pre-import guard, comprehensive SQLite and PostgreSQL URL validation, safe error reporting, and `pytest_sessionstart()` engine parity and live identity checks. | 361 | 12 | **MODIFIED (Verified)** |

---

## 3. Changes to Startup Schema Safety (`backend/app/main.py`)

### 3.1 Defect Remediated
Previously, `lifespan(app)` executed unconditional `Base.metadata.create_all(bind=engine)` at Line 33 without dialect gating, environment checking, or target path authorization.

### 3.2 Implemented Policy
- **Dialect Gating:** Dialect is extracted directly from `engine.dialect.name`.
- **SQLite Restrictions:**
  - Auto-DDL is permitted **only** when `settings.ENVIRONMENT == "development"` AND the target database is either:
    1. `:memory:` (or empty string), or
    2. Canonical `(BACKEND_DIR / "oliver_dev.db").resolve(strict=False)`.
  - Relative SQLite paths are resolved deterministically relative to `PROJECT_ROOT`, eliminating process-working-directory drift.
  - Any unauthorized SQLite target (e.g. `database/oliver.db`) or non-development environment immediately raises a fatal `RuntimeError` and terminates startup. Silent fallback is prohibited.
- **PostgreSQL Restrictions:**
  - `Base.metadata.create_all()` is strictly barred from execution on PostgreSQL.
  - Inspects `backend/alembic/versions/` using `alembic.script.ScriptDirectory`.
  - Fails closed with `RuntimeError` if:
    1. Zero Alembic migrations exist.
    2. Multiple migration heads exist (diverged branches).
    3. The database has no applied migration revision.
    4. The database contains multiple applied revision heads.
    5. The applied database revision does not match the script directory head.
- **Unsupported Dialects:** Any unrecognized database dialect raises `RuntimeError` immediately.

---

## 4. Changes to Test Isolation (`backend/tests/conftest.py`)

### 4.1 Pre-Import Execution (Line 1 Guard)
- The test isolation guard runs at Line 1 of `conftest.py`, before importing `backend.app.core.database`, `backend.app.main`, or any module that instantiates settings or database engines.
- `PROJECT_ROOT` is inserted into `sys.path`.
- Uses SQLAlchemy `make_url()` for robust, specification-compliant URL parsing.

### 4.2 Explicit Test-Mode Enforcement
- `OLIVER_TEST_MODE` must be explicitly configured in the environment:
  - SQLite database target requires `OLIVER_TEST_MODE="category_a"`.
  - PostgreSQL database target requires `OLIVER_TEST_MODE="category_b"`.
- Implicit defaulting to `category_a` is completely removed. Missing, empty, or contradictory test modes terminate execution immediately with `sys.exit(1)`.
- Validated test mode and URL object are stored in immutable module-level constants `_EXPECTED_TEST_MODE` and `_EXPECTED_TEST_URL_OBJECT`.

### 4.3 Category A (SQLite) Isolation Rules
- **Permitted Targets:** In-memory (`sqlite:///:memory:`, `sqlite+pysqlite:///:memory:`) or temporary files strictly contained within `backend/tests/.tmp`.
- **Prohibited Targets:** `database/oliver.db`, `backend/oliver_dev.db`, and any persistent database outside `.tmp`.
- **Driver Restrictions:** Synchronous drivers only (`sqlite`, `sqlite+pysqlite`).
- **Query Parameter Rules:** Rejects `uri=true`. `check_same_thread` is validated against `("true", "false", "0", "1")`. All other parameters are rejected.

### 4.4 Category B (PostgreSQL) Isolation Rules
- **Driver:** Strictly `postgresql+psycopg`.
- **Database:** Strictly `oliver_test` (`oliver_db` is strictly barred).
- **Username:** Strictly `oliver_test_user`.
- **Host:** Strictly loopback (`127.0.0.1` or `localhost`).
- **Port:** Explicitly specified as `5432`.
- **Query Parameters:** None permitted (empty dict).

---

## 5. Test Engine URL Parity Verification

In `pytest_sessionstart()`:
1. **Test-Mode Mutation Check:** Verifies `os.environ.get("OLIVER_TEST_MODE") == _EXPECTED_TEST_MODE`.
2. **Actual Engine Extraction:** Extracts `actual_url = app_engine.url` from the live application engine instance.
3. **Independent Validation:** Independently validates `actual_url` against Category A or Category B constraints.
4. **Parity Check:**
   - Category A: Verifies dialect is SQLite, driver is synchronous, and database targets match (in-memory match or canonical path match).
   - Category B: Verifies dialect is PostgreSQL, driver is `postgresql+psycopg`, database is `oliver_test`, user is `oliver_test_user`, host is loopback, and port is 5432.
5. **Early-Created Engine Detection:** If an unauthorized engine was created by a third-party plugin before `conftest.py` executed, the disparity between `app_engine.url` and `_EXPECTED_TEST_URL_OBJECT` triggers an immediate `RuntimeError("SECURITY ABORT: ...")` before any test function or fixture can run.

---

## 6. PostgreSQL Security Identity Checks

When running under `OLIVER_TEST_MODE="category_b"`, `pytest_sessionstart()` connects to the database and verifies nine live security invariants:
1. `curr_db == 'oliver_test'` (Target database is test database).
2. `curr_user == 'oliver_test_user'` (Active user is test user).
3. `sess_user == 'oliver_test_user'` (Session user is test user; no unvalidated `SET ROLE` elevation).
4. `not is_super` (Test user is not superuser).
5. `not is_db_owner` (Test user is not a member of `pg_database_owner`).
6. `tx_ro == 'off'` (Transaction is read-write for test fixtures).
7. Database owner query: `db_owner == 'oliver_migrator'` (`oliver_test` database is owned by cluster migrator).
8. Public schema owner query: `schema_owner == 'oliver_test_user'` (`public` schema within `oliver_test` is owned by test user).
9. Safe SQL NULL handling: Row existence is verified, and fields are checked with safe boolean coercion.

---

## 7. Windows Path Safety Defenses

The SQLite path validator in `conftest.py` defends against all identified Windows filesystem quirks:
- **Trailing Dots and Spaces:** Rejects trailing dots or spaces in **any** path component (`part.endswith((".", " "))`), preventing Win32 subsystem automatic normalization bypasses.
- **UNC Paths & Device Namespaces:** Rejects paths starting with `\\\\` (`\\server\share`, `\\.\`, `\\?\`).
- **Drive-Relative Paths:** Rejects paths of the form `C:file.db` or `C:folder\file.db`.
- **Reserved DOS Device Stems:** Rejects `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9` in any component stem.
- **URL-Encoded Paths:** Rejects `%` characters to prevent URL-encoding traversal bypasses.
- **NTFS Alternate Data Streams:** Rejects `:` anywhere after the drive letter (index > 1).
- **Symlink & Junction Containment:** Resolves target canonically and verifies strict containment inside `backend/tests/.tmp`.

---

## 8. Credential-Safe Error Handling

- Custom validation exceptions use explicit categorical messages detailing the violated rule without printing connection strings.
- Generic exceptions in URL parsing are caught and reported via a fixed message:  
  `"CRITICAL TEST ISOLATION ERROR: Database connection URL is malformed, contains invalid syntax, or failed parsing."`
- Passwords and raw URLs are never printed to `sys.stderr`, logged, or included in exception bodies.

---

## 9. Static & Syntax Verification Performed

In strict adherence to the read-only verification boundary:
- **Compilation Check:** Executed `python -m py_compile backend/app/main.py backend/tests/conftest.py`. Both files compiled cleanly with exit code 0.
- **Static Code Review:** Confirmed all imports, classes, functions, route registrations, middlewares (`log_requests`), fixtures, and exception handlers are intact and syntactically correct.
- **Working Tree Inspection:** Confirmed via `git status --short` that only the two authorized files were modified.

---

## 10. Tests Not Executed and Why

- **Execution Boundary Compliance:** No tests (`pytest`, `python -m pytest`, or `uvicorn`) were executed during this stage.
- **Reasoning:**
  1. The user instructions explicitly prohibited running test suites or starting FastAPI/Uvicorn during Stage 2.1A.0 verification.
  2. Running pytest requires explicitly passing `OLIVER_TEST_MODE="category_a"`, which was not authorized to run in this turn.
  3. All 14 Category A tests were statically reviewed; their fixtures (`client`, `db_session`, `test_engine`) and dependency overrides (`get_db`) are fully preserved and wire into `sqlite:///:memory:`.

---

## 11. Git Diff Summary

```
$ git diff --stat
 backend/app/main.py       | 113 ++++++++++++++-
 backend/tests/conftest.py | 361 ++++++++++++++++++++++++++++++++++++++++++++--
 2 files changed, 458 insertions(+), 16 deletions(-)
```

---

## 12. Database Preservation Confirmation

Both persistent SQLite databases were verified via physical file metadata after all edits were completed:

| Database File | Absolute Path | Size (Bytes) | Last Modified | Status |
|---|---|---|---|---|
| **Desktop SQLite** | `database/oliver.db` | 192,512 | 07-11-2026 19:38:26 | **INTACT & UNMODIFIED** |
| **Backend Dev SQLite** | `backend/oliver_dev.db` | 94,208 | 07-11-2026 18:12:44 | **INTACT & UNMODIFIED** |

- Neither database was opened, connected to, or modified.
- No `-wal` or `-shm` sidecar files exist.

---

## 13. Unresolved Defects or Limitations

1. **Alembic Initial Migration Pending (Stage 2.1A.3):**
   - Direct inspection confirms `backend/alembic/versions/` contains zero migrations (`.gitkeep` only).
   - Under the newly implemented fail-closed startup policy, starting the central backend against PostgreSQL will deliberately fail closed. This is the desired behavior until Stage 2.1A.3 generates and applies the baseline migration.
2. **PostgreSQL Driver Packaging (Stage 2.1A.5):**
   - `psycopg` is not yet installed in the virtual environment. Category B tests and PostgreSQL connections remain blocked until Stage 2.1A.5.
3. **Subsequent Stages Unauthorized:**
   - Stages 2.1A.1 through 2.1A.8 remain strictly unauthorized and have not been started.

---

## 14. Acceptance Criteria Checklist

- [x] Exactly two authorized source files modified (`backend/app/main.py` and `backend/tests/conftest.py`).
- [x] Zero existing user work overwritten; all routers, middlewares, endpoints, and fixtures preserved.
- [x] SQLite startup schema creation restricted to approved development targets (`backend/oliver_dev.db` and `:memory:`).
- [x] PostgreSQL startup barred from invoking `create_all()`.
- [x] PostgreSQL schema verification fails closed on missing/divergent Alembic heads or unmigrated databases.
- [x] Test database isolation guard executes at Line 1 before application imports.
- [x] Actual application engine URL independently verified against expected test URL in `pytest_sessionstart()`.
- [x] Category A and Category B requirements explicit and strictly enforced; implicit defaulting removed.
- [x] No credentials leak through error messages or logs.
- [x] Zero persistent database or infrastructure operations occurred.
- [x] Exactly one implementation report created (`docs/OLIVER_3_PHASE_2_1A0_IMPLEMENTATION_REPORT.md`).
- [x] All unresolved issues and limits documented honestly.

---

## 15. Stop Condition

Stage 2.1A.0 implementation is complete. Execution is halted immediately. Awaiting next user explicit instruction.
