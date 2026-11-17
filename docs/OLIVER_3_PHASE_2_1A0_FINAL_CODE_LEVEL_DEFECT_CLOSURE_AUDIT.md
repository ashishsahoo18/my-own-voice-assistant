# OLIVER 3.0 — Stage 2.1A.0 Final Code-Level Defect Closure Audit

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A0_FINAL_CODE_LEVEL_DEFECT_CLOSURE_AUDIT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Migration  
**Stage:** 2.1A.0 — Startup Safety and Test Isolation  
**Audit Mode:** STRICTLY READ-ONLY AUDIT  
**Target Environment:** Windows 10/11, Python 3.13.5 AMD64, Docker Desktop (WSL2), PostgreSQL 16, psycopg 3.x, Alembic  
**Preceding Audit Documents:** `docs/OLIVER_3_PHASE_2_1A0_FINAL_PRE_IMPLEMENTATION_SECURITY_CORRECTION_AUDIT.md` (v15.0) and predecessors (v1.0–v14.0)  
**Execution Boundary:** STRICTLY READ-ONLY AUDIT. Zero application source modifications, zero test modifications, zero package installations, zero container execution, zero database writes.

---

## 1. Executive Summary

This independent technical audit performs the final, code-level defect closure review for **Stage 2.1A.0 (Startup Safety and Test Isolation)** before any source code edits are executed in the repository.

Stage 2.1A.0 is strictly confined to two files:
1. `backend/app/main.py` (Fail-closed schema initialization and Alembic revision gating).
2. `backend/tests/conftest.py` (Pre-import test isolation guard, URL validation, and live session verification).

A rigorous line-by-line review of the code proposals in audit reports v14.0 and v15.0 revealed six remaining implementation defects:
1. **Unverified Application Engine URL in `pytest_sessionstart()`:** Earlier proposals claimed `pytest_sessionstart()` verified `app_engine.url`, but the actual supplied code only inspected PostgreSQL connection identity via SQL in Category B, while performing **zero checks** on `app_engine.url` for Category A. If a third-party plugin initialized `app_engine` pointing to `database/oliver.db` prior to `conftest.py`, Category A tests would have executed without detecting the invalid engine.
2. **Implicit Test Mode Defaulting:** Report v15.0 automatically assigned `OLIVER_TEST_MODE="category_a"` when the environment variable was omitted. Automatic assignment creates an implicit bypass path where an unintended SQLite execution proceeds without explicit operator intent.
3. **Incomplete Windows Path Traversal & Component Normalization:** The proposed SQLite path validator inspected trailing dots and spaces only on the leaf filename. On Windows, trailing dots and spaces in intermediate directory components (e.g., `folder. \subfolder\file.db`) are stripped by the Win32 subsystem. Furthermore, URL-encoding (`%2e%2e`), NTFS Alternate Data Streams (`test.db:stream`), and 8.3 short names were unhandled.
4. **Credential Exposure Risk in Error Handlers:** Printing arbitrary exception text from URL parsers can leak cleartext database passwords if connection strings are malformed.
5. **Non-Deterministic Relative Path Resolution in `main.py`:** `Path(db_file).resolve()` resolved relative SQLite paths against the active process working directory (`os.getcwd()`), which varies depending on where uvicorn or pytest is launched, rather than the canonical project root.
6. **Ambiguity Between Static Analysis and Runtime Verification:** Clarification is required to explicitly distinguish static inspection of the 14 existing backend tests from actual runtime execution. No tests were run during this read-only audit.

All six defects have been definitively resolved in the implementation designs presented in this report.

**Final Verdict:** **`READY FOR STAGE 2.1A.0 IMPLEMENTATION`**

---

## 2. Actual Repository Baseline & Physical Inventory

### 2.1 Git Status & Commit Hierarchy

A strictly read-only inspection of the repository working tree and commit log establishes:
- **Active Branch:** `main`
- **HEAD Commit:** `87f7230` (`Create OLIVER_3_PHASE_2_1A_FINAL_TECHNICAL_CORRECTION_AUDIT.md`)
- **Preceding Commit:** `1307956` (`Create OLIVER_3_PHASE_2_1A_PRE_IMPLEMENTATION_CORRECTION_PLAN.md`)
- **Tracked Modifications:** 0 files modified, 0 files deleted.
- **Untracked Audit Reports On Disk:**
  - `docs/OLIVER_3_PHASE_2_1A_FINAL_ISOLATION_PROVISIONING_BACKUP_SAFETY_AUDIT.md` (v11.0, 42,704 bytes)
  - `docs/OLIVER_3_PHASE_2_1A_FINAL_CONTRADICTION_RESOLUTION_AUDIT.md` (v12.0, 42,853 bytes)
  - `docs/OLIVER_3_PHASE_2_1A_FINAL_SECURITY_BOUNDARY_SNAPSHOT_AUDIT.md` (v13.0, 31,507 bytes)
  - `docs/OLIVER_3_PHASE_2_1A_FINAL_STAGE_2A0_AUTHORIZATION_AUDIT.md` (v14.0, 31,048 bytes)
  - `docs/OLIVER_3_PHASE_2_1A0_FINAL_PRE_IMPLEMENTATION_SECURITY_CORRECTION_AUDIT.md` (v15.0, 31,894 bytes)

### 2.2 Physical Database Integrity & Invariant Verification

Both persistent SQLite databases were physically verified via file-system metadata:

| Database File | Absolute Path | Size (Bytes) | Last Modified | Invariant Status |
|---|---|---|---|---|
| **Desktop SQLite** | `database/oliver.db` | 192,512 | 07-11-2026 19:38:26 | **INTACT & UNMODIFIED.** Zero mutations permitted. |
| **Backend Dev SQLite** | `backend/oliver_dev.db` | 94,208 | 07-11-2026 18:12:44 | **INTACT & UNMODIFIED.** Offline dev reference only. |

- No `-wal` or `-shm` sidecar files exist in `database/` or `backend/`.
- Neither database was opened or modified during this audit.

### 2.3 Inspected Files & Relevant Line Numbers

| File Inspected | Line Range | Key Code Inspected | Defect / Observation |
|---|---|---|---|
| `backend/app/main.py` | Lines 28–37 | `lifespan(app)` context manager | Line 33 executes unconditional `Base.metadata.create_all(bind=engine)` without checking dialect, target path, or environment. |
| `backend/tests/conftest.py` | Lines 16–25 | Module imports | Lines 21–23 import `backend.app.core.database` and `backend.app.main` before any isolation fixture or pre-import guard runs. |
| `backend/app/core/database.py` | Lines 12–23 | Engine creation | Lines 17–22 instantiate `engine = create_engine(settings.DATABASE_URL)` at import time. |
| `backend/app/core/config.py` | Lines 31–34, 61 | Settings instantiation | Line 32 defines default `DATABASE_URL` pointing to `oliver_dev.db`; Line 61 instantiates global `settings = Settings()`. |
| `backend/alembic/versions/` | Entire Directory | `.gitkeep` | Contains only `.gitkeep` (41 bytes). **ZERO MIGRATIONS EXIST.** |
| `backend/tests/test_auth.py` | Lines 6–125 | 7 unit tests | Statically inspected; uses `client` fixture wired to in-memory SQLite. |
| `backend/tests/test_endpoints.py` | Lines 6–75 | 3 integration tests | Statically inspected; uses `client` fixture wired to in-memory SQLite. |
| `backend/tests/test_isolation.py` | Lines 6–74 | 1 multi-tenant test | Statically inspected; uses `client` fixture. |
| `backend/tests/test_tokens.py` | Lines 13–81 | 3 token tests | Statically inspected; uses `client` and `db_session`. |

---

## 3. Critical Fix 1: Verification of the Actual Application Engine URL

### 3.1 Defect Analysis in Earlier Proposals

In report v15.0 Section 4.5, `pytest_sessionstart()` contained:
```python
def pytest_sessionstart(session):
  test_mode = os.getenv("OLIVER_TEST_MODE", "category_a").strip().lower()
  if test_mode == "category_b":
    with app_engine.connect() as conn:
      # Ran PostgreSQL identity queries...
```
**Fatal Flaw:**
- In Category A (the active mode for all existing unit tests), `pytest_sessionstart()` executed **zero checks**.
- It did not inspect `app_engine.url`.
- If an unapproved engine was created prior to `conftest.py` (e.g. by an early-loading pytest plugin or script), `app_engine` could be pointing to `backend/oliver_dev.db` or `database/oliver.db`. Category A tests would proceed, and entering `TestClient(app)` lifespan would trigger DDL against the wrong database.
- Even in Category B, `pytest_sessionstart()` connected to the database before verifying that `app_engine.url.host`, `port`, `database`, and `username` matched the validated test configuration.

### 3.2 Corrected Two-Stage Engine URL Verification Design

1. **Stage 1 (Pre-Import Guard):** Validates the incoming environment URL, binds it to an immutable module-level expected object `_EXPECTED_TEST_URL_OBJECT`, and locks `os.environ["DATABASE_URL"]`.
2. **Stage 2 (Session-Start Independent Validation):** In `pytest_sessionstart()`, before any fixture or test executes:
   - Extract `actual_url = app_engine.url`.
   - Independently parse and validate `actual_url` against the strict driver, database, host, port, and query parameter constraints.
   - Assert exact parity between `actual_url` and `_EXPECTED_TEST_URL_OBJECT`:
     - For Category A: Confirm backend is `sqlite`, driver is synchronous, target matches the expected in-memory database or canonically matches the expected file within `backend/tests/.tmp`.
     - For Category B: Confirm backend is `postgresql`, driver is `postgresql+psycopg`, database is `oliver_test`, user is `oliver_test_user`, host is loopback, port is explicitly 5432, and query parameters are empty.
   - Any discrepancy raises `RuntimeError("SECURITY ABORT: Application engine URL target mismatch...")` and fails closed immediately.

### 3.3 How This Detects Engines Created Before `conftest.py`

If a third-party pytest plugin (registered via `pytest.ini` or `-p plugin_name`) imports `backend.app.core.database` before pytest loads the root `conftest.py`:
1. Python executes `backend.app.core.config`, instantiating `settings` with whatever `DATABASE_URL` was present in `.env` (typically `backend/oliver_dev.db`).
2. Python executes `backend.app.core.database`, instantiating `engine = create_engine(...)` bound to `backend/oliver_dev.db`. Both modules are cached in `sys.modules`.
3. Pytest subsequently invokes `backend/tests/conftest.py`. Line 1 guard runs, validates `_EXPECTED_TEST_URL_OBJECT` (`sqlite:///:memory:`), and sets `os.environ["DATABASE_URL"] = "sqlite:///:memory:"`.
4. However, `backend.app.core.database.engine` was **already instantiated**. Modifying `os.environ` after instantiation does *not* rebuild an existing SQLAlchemy engine!
5. When `pytest_sessionstart()` runs, it inspects `app_engine.url`. It discovers:
   - `_EXPECTED_TEST_URL_OBJECT.database == ":memory:"`
   - `app_engine.url.database == "C:\\...\\backend\\oliver_dev.db"`
6. Parity assertion fails: `pytest_sessionstart()` immediately raises `RuntimeError` and terminates the test runner before any test function or fixture can execute.

---

## 4. Critical Fix 2: Explicit Test-Mode Enforcement

### 4.1 Defect Analysis: The Danger of Automatic Mode Assignment

Report v15.0 contained:
```python
if _backend_name == "sqlite":
  _validate_sqlite_url(_parsed_url)
  if not _test_mode:
    os.environ["OLIVER_TEST_MODE"] = "category_a"
```
**Vulnerability:**
Automatic defaulting to `category_a` allows ambiguous test configurations to proceed without explicit operator confirmation. If an operator configures an environment without specifying the test mode, the system assumes Category A, potentially masking intent or creating divergent behaviors across CI pipelines.

### 4.2 Corrected Fail-Closed Enforcement

The guard strictly mandates explicit configuration:
- `OLIVER_TEST_MODE` must be explicitly defined in `os.environ`.
- If missing or empty: **Fail closed immediately**.
- If `DATABASE_URL` is SQLite: `OLIVER_TEST_MODE` must be explicitly `"category_a"`.
- If `DATABASE_URL` is PostgreSQL: `OLIVER_TEST_MODE` must be explicitly `"category_b"`.
- Any other value or contradiction raises a fatal error and calls `sys.exit(1)`.
- The validated mode is stored in an immutable module-level constant `_EXPECTED_TEST_MODE`.
- In `pytest_sessionstart()`, `os.environ.get("OLIVER_TEST_MODE")` is re-checked against `_EXPECTED_TEST_MODE` to guarantee the mode was not mutated at runtime.

---

## 5. Critical Fix 3: Hardened Windows Path Validation

### 5.1 Comprehensive Windows Bypass Vectors & Defenses

| Vulnerability Vector | Mechanism of Attack | Hardened Defensive Implementation |
|---|---|---|
| **Trailing Dots & Spaces** | Win32 subsystem strips trailing dots and spaces in all path components (`folder. \file.db.` -> `folder\file.db`), allowing bypass of string filters. | Inspects `Path(raw_path).parts`. Rejects any component where `part.endswith((".", " "))`. |
| **UNC & Network Shares** | Paths starting with `\\` or `//` (`\\attacker\share\db.db`) trigger network egress or SMB authentication. | Normalizes slashes and rejects paths starting with `\\\\`. |
| **DOS Device Namespaces** | `\\.\` and `\\?\` bypass Win32 path normalization and security hooks. | Rejected by the `\\\\` prefix check. |
| **Drive-Relative Paths** | `C:file.db` or `C:folder\file.db` (without leading slash) resolves relative to drive C's working directory. | Rejects paths where `path[1] == ':'` and the third character is not `\\` or `/`. |
| **Reserved DOS Device Stems** | `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9` in any component lock kernel devices. | Inspects every path component in `parts`. Checks `part.split('.')[0].lower()` against `_RESERVED_DOS_NAMES`. |
| **URL-Encoded Paths** | `%2e%2e` (`..`), `%2f` (`/`), `%5c` (`\`), `%00` (null byte) evade string filters before decoding. | Rejects any SQLite database path containing `%`. |
| **NTFS Alternate Data Streams** | `test.db:stream` writes hidden streams outside standard file monitoring. | Rejects `:` appearing anywhere after the drive letter (index > 1). |
| **Symlinks & Reparse Points** | Directory junctions or symlinks pointing outside `.tmp`. | Resolves canonical path via `Path.resolve(strict=False)`. Enforces strict containment inside `APPROVED_TEST_TMP_DIR`. |

### 5.2 Documented Platform Limitations & Defenses
- **8.3 Short Filename Aliases (e.g., `OLIVER~1.DB`):** If 8.3 naming is enabled on the NTFS volume, `backend/oliver_dev.db` could have an alias. However, because our guard mandates that the canonical target must reside strictly inside `backend/tests/.tmp`, even an 8.3 alias pointing to a file in `.tmp` remains safely contained within `.tmp`. `oliver_dev.db` resides in `backend/` and cannot resolve inside `backend/tests/.tmp`.

---

## 6. Critical Fix 4: Safe Error Reporting (Credential Masking)

### 6.1 Vulnerability in Standard Exception Logging
If a malformed connection string (e.g., `postgresql+psycopg://user:P@ssword!@localhost:5432/db`) is parsed by `make_url` or a custom parser, the exception message might include the raw URL or user credentials:
```python
# INSECURE LOGGING
except Exception as _exc:
  print(f"Error: {_exc}", file=sys.stderr)  # Can output cleartext password!
```

### 6.2 Hardened Safe Error Handler
All error reporting uses sanitized, categorical messages:
```python
except ValueError as _ve:
  # Our custom validation errors contain strictly sanitized strings with zero secrets
  print(f"CRITICAL TEST ISOLATION ERROR: {_ve}", file=sys.stderr)
  sys.exit(1)
except Exception:
  # Generic parsing exceptions: never print the exception body
  print(
      "CRITICAL TEST ISOLATION ERROR: Database connection URL is malformed,"
      " contains invalid syntax, or failed parsing.",
      file=sys.stderr,
  )
  sys.exit(1)
```

---

## 7. Critical Fix 5: Deterministic SQLite Path Resolution in `main.py`

### 7.1 Defect Analysis: Working-Directory Drift
In report v15.0, `main.py` resolved `Path(db_file).resolve(strict=False)`.
- If `db_file` is relative (e.g. `sqlite:///oliver_dev.db`), `Path.resolve()` resolves against `os.getcwd()`.
- If uvicorn is launched from `backend/app/`, `os.getcwd()` is `backend/app/`.
- If launched from project root, `os.getcwd()` is `my own voice assistant/`.
- This working-directory dependence breaks deterministic verification.

### 7.2 Corrected Deterministic Root Resolution
In `backend/app/main.py`:
```python
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
AUTHORIZED_DEV_DB = (BACKEND_DIR / "oliver_dev.db").resolve(strict=False)

# Deterministic resolution:
if not Path(db_file).is_absolute():
  resolved_target = (PROJECT_ROOT / db_file).resolve(strict=False)
else:
  resolved_target = Path(db_file).resolve(strict=False)
```
This guarantees that relative paths are always evaluated relative to the repository project root, eliminating working-directory drift.

---

## 8. Authoritative Stage 2.1A.0 Code Implementations

### 8.1 Authoritative Code for `backend/app/main.py`

```python
"""Main FastAPI application entry point for OLIVER 3.0 Central Backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.core.config import settings
from backend.app.core.database import Base, engine
from backend.app.core.limiter import limiter
from backend.app.core.logging import logger
from backend.app.routers import (
    auth_router,
    chat_router,
    devices_router,
    health_router,
    user_router,
    welcome_router,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
AUTHORIZED_DEV_DB = (BACKEND_DIR / "oliver_dev.db").resolve(strict=False)


def _verify_startup_schema() -> None:
  """Enforce strict fail-closed database initialization and migration head checks."""
  dialect_name = engine.dialect.name

  if dialect_name == "sqlite":
    db_file = engine.url.database
    is_memory = not db_file or db_file == ":memory:"

    if not is_memory:
      raw_path = Path(db_file)
      resolved_target = (
          (PROJECT_ROOT / raw_path).resolve(strict=False)
          if not raw_path.is_absolute()
          else raw_path.resolve(strict=False)
      )
      is_authorized = resolved_target == AUTHORIZED_DEV_DB
    else:
      is_authorized = True

    if settings.ENVIRONMENT == "development" and is_authorized:
      logger.info(
          "Development SQLite detected. Initializing schema via create_all()..."
      )
      Base.metadata.create_all(bind=engine)
      return

    # Non-development or unauthorized SQLite target -> Fail closed immediately
    error_msg = (
        f"FATAL STARTUP BLOCKED: create_all() is unauthorized for SQLite target"
        f" in environment '{settings.ENVIRONMENT}'. Auto-DDL is permitted"
        f" strictly for '{AUTHORIZED_DEV_DB}' in 'development' mode."
    )
    logger.critical(error_msg)
    raise RuntimeError(error_msg)

  elif dialect_name in ("postgresql", "postgresql+psycopg"):
    logger.info(
        "PostgreSQL backend detected. Verifying Alembic migration status..."
    )
    script_location = (BACKEND_DIR / "alembic").resolve()

    if not script_location.exists():
      raise RuntimeError(
          f"FATAL STARTUP BLOCKED: Alembic directory not found at"
          f" {script_location}"
      )

    script_dir = ScriptDirectory(str(script_location))
    heads = script_dir.get_heads()

    if not heads:
      error_msg = (
          "FATAL STARTUP BLOCKED: No Alembic migrations exist in"
          " backend/alembic/versions/. PostgreSQL requires managed migrations."
      )
      logger.critical(error_msg)
      raise RuntimeError(error_msg)

    if len(heads) > 1:
      error_msg = (
          f"FATAL STARTUP BLOCKED: Multiple Alembic migration heads detected:"
          f" {heads}. Migration branches must be merged via 'alembic merge'"
          " before startup."
      )
      logger.critical(error_msg)
      raise RuntimeError(error_msg)

    expected_head = heads[0]

    with engine.connect() as conn:
      context = MigrationContext.configure(conn)
      current_heads = context.get_current_heads()

    if not current_heads:
      error_msg = (
          "FATAL STARTUP BLOCKED: Database has no applied Alembic revisions"
          f" (unmigrated). Expected migration head: '{expected_head}'."
      )
      logger.critical(error_msg)
      raise RuntimeError(error_msg)

    if len(current_heads) > 1:
      error_msg = (
          f"FATAL STARTUP BLOCKED: Database contains multiple applied revision"
          f" heads: {current_heads}."
      )
      logger.critical(error_msg)
      raise RuntimeError(error_msg)

    current_rev = current_heads[0]
    if current_rev != expected_head:
      error_msg = (
          f"FATAL STARTUP BLOCKED: Database revision '{current_rev}' does not"
          f" match expected Alembic head '{expected_head}'."
      )
      logger.critical(error_msg)
      raise RuntimeError(error_msg)

    logger.info(
        "Alembic migration head verified successfully: revision %s", current_rev
    )
    return

  else:
    error_msg = f"FATAL STARTUP BLOCKED: Unsupported database dialect '{dialect_name}'."
    logger.critical(error_msg)
    raise RuntimeError(error_msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
  """Application lifespan context: verify schema readiness before accepting requests."""
  logger.info("Verifying database schema readiness for OLIVER 3.0...")
  _verify_startup_schema()
  logger.info(
      "OLIVER 3.0 Central Backend started successfully on %s:%d",
      settings.HOST,
      settings.PORT,
  )
  yield
  logger.info("Shutting down OLIVER 3.0 Central Backend...")


app = FastAPI(
    title="OLIVER 3.0 Central Backend",
    description=(
        "Central AI orchestration, authentication, and cross-device sync"
        " service for OLIVER."
    ),
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Middleware
origins = (
    settings.CORS_ORIGINS
    if isinstance(settings.CORS_ORIGINS, list)
    else [settings.CORS_ORIGINS]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(welcome_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(devices_router)
app.include_router(chat_router)
```

---

### 8.2 Authoritative Code for `backend/tests/conftest.py`

```python
"""Pytest configuration and test database fixtures for OLIVER 3.0."""

from __future__ import annotations

import os
from pathlib import Path
import sys

# ==============================================================================
# STAGE 2.1A.0 PRE-IMPORT TEST ISOLATION GUARD (LINE 1 EXECUTION)
# ==============================================================================
# Must execute before ANY application or database modules are imported.

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.engine import make_url

_RESERVED_DOS_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

APPROVED_TEST_TMP_DIR = (
    PROJECT_ROOT / "backend" / "tests" / ".tmp"
).resolve()


def _validate_sqlite_url(url) -> None:
  """Validate that a SQLite URL conforms to strict test isolation constraints."""
  # 1. Driver allowlist: synchronous drivers only
  if url.drivername not in ("sqlite", "sqlite+pysqlite"):
    raise ValueError(
        f"Unauthorized test SQLite driver '{url.drivername}'. "
        "Allowed drivers: 'sqlite', 'sqlite+pysqlite'."
    )

  # 2. Query parameter validation
  query_params = dict(url.query)
  if "uri" in query_params or query_params.get("uri") == "true":
    raise ValueError("SQLite URI mode ('uri=true') is prohibited in test URLs.")

  if "check_same_thread" in query_params:
    val = str(query_params.pop("check_same_thread")).lower()
    if val not in ("true", "false", "0", "1"):
      raise ValueError(f"Invalid check_same_thread value: '{val}'.")

  if query_params:
    raise ValueError(
        f"Unauthorized query parameters in test SQLite URL: {list(query_params.keys())}"
    )

  # 3. Path inspection
  db_path = url.database
  if not db_path or db_path == ":memory:":
    return  # In-memory database is unconditionally safe

  raw_path = str(db_path)

  # Reject URL-encoded characters
  if "%" in raw_path:
    raise ValueError(
        "URL-encoded characters are prohibited in SQLite test database paths."
    )

  # Reject NTFS Alternate Data Streams (colon beyond drive letter index 1)
  after_drive = (
      raw_path[2:]
      if (len(raw_path) >= 2 and raw_path[1] == ":")
      else raw_path
  )
  if ":" in after_drive:
    raise ValueError(
        "NTFS Alternate Data Streams (':') are prohibited in test database"
        " paths."
    )

  # Reject trailing dots and spaces in ANY path component (Windows Win32 bypass)
  path_obj = Path(raw_path)
  for part in path_obj.parts:
    if part not in ("\\", "/") and part.endswith((".", " ")):
      raise ValueError(
          "Path components with trailing dots or spaces are prohibited on"
          f" Windows: '{part}'."
      )

  # Reject UNC paths and DOS device namespaces
  norm_path = raw_path.replace("/", "\\")
  if norm_path.startswith("\\\\"):
    raise ValueError(
        "UNC paths and DOS device namespaces (\\\\.\\, \\\\?\\) are"
        " prohibited."
    )

  # Reject drive-relative paths (e.g. C:file.db without root slash)
  if (
      len(raw_path) >= 2
      and raw_path[1] == ":"
      and not (len(raw_path) > 2 and raw_path[2] in ("\\", "/"))
  ):
    raise ValueError(
        "Drive-relative paths without a root directory separator are"
        " prohibited."
    )

  # Reject reserved DOS device names in any component
  for part in path_obj.parts:
    stem = part.split(".")[0].lower()
    if stem in _RESERVED_DOS_NAMES:
      raise ValueError(
          f"Reserved DOS device name prohibited in path component: '{stem}'."
      )

  # Resolve canonical path (handles symlinks and directory junctions)
  target_file = (
      (PROJECT_ROOT / path_obj).resolve(strict=False)
      if not path_obj.is_absolute()
      else path_obj.resolve(strict=False)
  )

  # Enforce containment strictly inside approved test temp directory
  try:
    target_file.relative_to(APPROVED_TEST_TMP_DIR)
  except ValueError:
    raise ValueError(
        "Test SQLite database path must reside strictly within"
        f" '{APPROVED_TEST_TMP_DIR}'."
    )

  if target_file == APPROVED_TEST_TMP_DIR:
    raise ValueError(
        "Test SQLite database path cannot be the .tmp directory itself."
    )


def _validate_postgres_test_url(url) -> None:
  """Validate that a PostgreSQL URL conforms to Category B test isolation constraints."""
  if url.drivername != "postgresql+psycopg":
    raise ValueError(
        f"Category B test driver must be 'postgresql+psycopg', got '{url.drivername}'."
    )

  if url.database != "oliver_test":
    raise ValueError(
        f"Category B test database must be 'oliver_test', got '{url.database}'."
    )

  if url.username != "oliver_test_user":
    raise ValueError(
        f"Category B test user must be 'oliver_test_user', got '{url.username}'."
    )

  if url.host not in ("127.0.0.1", "localhost"):
    raise ValueError(
        f"Category B test host must be loopback (127.0.0.1 or localhost), got '{url.host}'."
    )

  if url.port is None or int(url.port) != 5432:
    raise ValueError(
        f"Category B test port must be explicitly 5432, got '{url.port}'."
    )

  if url.query:
    raise ValueError("Category B test URL must not contain query parameters.")


# Enforce explicit test mode configuration
_raw_mode = os.environ.get("OLIVER_TEST_MODE")
if _raw_mode is None or not _raw_mode.strip():
  print(
      "CRITICAL TEST ISOLATION ERROR: OLIVER_TEST_MODE environment variable is"
      " not set. You must explicitly configure OLIVER_TEST_MODE='category_a'"
      " (for SQLite unit tests) or OLIVER_TEST_MODE='category_b' (for"
      " PostgreSQL integration tests).",
      file=sys.stderr,
  )
  sys.exit(1)

_test_mode = _raw_mode.strip().lower()
if _test_mode not in ("category_a", "category_b"):
  print(
      f"CRITICAL TEST ISOLATION ERROR: Invalid OLIVER_TEST_MODE '{_test_mode}'."
      " Allowed values: 'category_a', 'category_b'.",
      file=sys.stderr,
  )
  sys.exit(1)

# Default to in-memory SQLite if DATABASE_URL is not set
_current_test_db = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

try:
  _parsed_url = make_url(_current_test_db)
  _backend_name = _parsed_url.get_backend_name()

  if _backend_name == "sqlite":
    if _test_mode != "category_a":
      raise ValueError(
          "Contradictory test configuration: SQLite database URL specified,"
          f" but OLIVER_TEST_MODE is '{_test_mode}'. Expected 'category_a'."
      )
    _validate_sqlite_url(_parsed_url)
  elif _backend_name == "postgresql":
    if _test_mode != "category_b":
      raise ValueError(
          "Contradictory test configuration: PostgreSQL database URL specified,"
          f" but OLIVER_TEST_MODE is '{_test_mode}'. Expected 'category_b'."
      )
    _validate_postgres_test_url(_parsed_url)
  else:
    raise ValueError(f"Unsupported test backend: '{_backend_name}'.")

except ValueError as _ve:
  # Safe sanitized output: prints explicit validation rules without exposing credentials
  print(f"CRITICAL TEST ISOLATION ERROR: {_ve}", file=sys.stderr)
  sys.exit(1)
except Exception:
  # Generic parsing exceptions: never print the raw exception text which might contain credentials
  print(
      "CRITICAL TEST ISOLATION ERROR: Database connection URL is malformed,"
      " contains invalid syntax, or failed parsing.",
      file=sys.stderr,
  )
  sys.exit(1)

# Retain validated URL object and mode as immutable module-level baselines
_EXPECTED_TEST_URL_OBJECT = _parsed_url
_EXPECTED_TEST_MODE = _test_mode

# Lock environment variables
os.environ["DATABASE_URL"] = _current_test_db
os.environ["ENVIRONMENT"] = "development"

# ==============================================================================
# STANDARD TEST FIXTURES & IMPORTS (SAFE TO IMPORT APP AFTER GUARD)
# ==============================================================================

from typing import Generator
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from backend.app.core.database import Base, engine as app_engine, get_db
from backend.app.core.limiter import limiter
from backend.app.main import app
from backend.app.services.ai_provider import AIProvider

# In-memory test engine for isolated unit testing
TEST_DB_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


class MockAIProvider(AIProvider):
  """Mock AI Provider for deterministic test execution."""

  async def generate_response(
      self, prompt: str, system_prompt: str = ""
  ) -> tuple[str, float]:
    clean = prompt.strip().lower()
    if "hello" in clean or "hi" in clean:
      return (
          "Hello! I am OLIVER, your personal AI assistant. How can I help"
          " you today?",
          1.0,
      )
    return f"Mock AI answer to: {prompt}", 15.0

  async def check_health(self) -> tuple[bool, str, str]:
    return True, "mock-llama3.2", ""


def pytest_sessionstart(session):
  """Secondary live defense: verify engine and database connection identity before test run."""
  # 1. Verify test mode invariant
  current_env_mode = os.environ.get("OLIVER_TEST_MODE", "").strip().lower()
  if current_env_mode != _EXPECTED_TEST_MODE:
    raise RuntimeError(
        "SECURITY ABORT: OLIVER_TEST_MODE was tampered with after initial guard."
        f" Expected '{_EXPECTED_TEST_MODE}', got '{current_env_mode}'."
    )

  # 2. Independently validate the actual app_engine.url
  actual_url = app_engine.url
  actual_backend = actual_url.get_backend_name()

  if _EXPECTED_TEST_MODE == "category_a":
    if actual_backend != "sqlite":
      raise RuntimeError(
          "SECURITY ABORT: Category A test runner detected non-SQLite"
          f" application engine dialect: '{actual_backend}'."
      )

    _validate_sqlite_url(actual_url)

    expected_db = _EXPECTED_TEST_URL_OBJECT.database
    actual_db = actual_url.database

    is_expected_mem = not expected_db or expected_db == ":memory:"
    is_actual_mem = not actual_db or actual_db == ":memory:"

    if is_expected_mem != is_actual_mem:
      raise RuntimeError(
          "SECURITY ABORT: Engine database target mismatch between expected"
          " and actual in-memory status."
      )

    if not is_expected_mem:
      exp_path = (
          (PROJECT_ROOT / Path(expected_db)).resolve(strict=False)
          if not Path(expected_db).is_absolute()
          else Path(expected_db).resolve(strict=False)
      )
      act_path = (
          (PROJECT_ROOT / Path(actual_db)).resolve(strict=False)
          if not Path(actual_db).is_absolute()
          else Path(actual_db).resolve(strict=False)
      )
      if exp_path != act_path:
        raise RuntimeError(
            "SECURITY ABORT: Engine database file path mismatch between"
            " expected and actual target."
        )

  elif _EXPECTED_TEST_MODE == "category_b":
    if actual_backend != "postgresql":
      raise RuntimeError(
          "SECURITY ABORT: Category B test runner detected non-PostgreSQL"
          f" application engine dialect: '{actual_backend}'."
      )

    _validate_postgres_test_url(actual_url)

    # Parity check
    if (
        actual_url.database != "oliver_test"
        or actual_url.username != "oliver_test_user"
        or actual_url.host not in ("127.0.0.1", "localhost")
        or actual_url.port != 5432
    ):
      raise RuntimeError(
          "SECURITY ABORT: Category B application engine URL parameters do not"
          " match strict isolation baseline."
      )

    # Live PostgreSQL connection verification
    with app_engine.connect() as conn:
      row = conn.execute(
          text("""
                SELECT 
                    current_database() AS curr_db,
                    current_user AS curr_user,
                    session_user AS sess_user,
                    usesuper AS is_super,
                    pg_has_role(current_user, 'pg_database_owner', 'MEMBER') AS is_db_owner,
                    current_setting('transaction_read_only') AS tx_ro
                FROM pg_user 
                WHERE usename = current_user;
            """)
      ).mappings().one_or_none()

      if row is None:
        raise RuntimeError(
            "SECURITY ABORT: Failed to retrieve user identity from pg_user."
        )

      if row["curr_db"] != "oliver_test":
        raise RuntimeError(
            f"SECURITY ABORT: Connected to database '{row['curr_db']}'"
            " instead of 'oliver_test'."
        )
      if row["curr_user"] != "oliver_test_user":
        raise RuntimeError(
            f"SECURITY ABORT: Connected as user '{row['curr_user']}'"
            " instead of 'oliver_test_user'."
        )
      if row["sess_user"] != "oliver_test_user":
        raise RuntimeError(
            f"SECURITY ABORT: Session user is '{row['sess_user']}'"
            " instead of 'oliver_test_user'."
        )
      if bool(row["is_super"]):
        raise RuntimeError(
            "SECURITY ABORT: Test user has superuser privileges."
        )
      if bool(row["is_db_owner"]):
        raise RuntimeError(
            "SECURITY ABORT: Test user is member of pg_database_owner."
        )
      if row["tx_ro"] != "off":
        raise RuntimeError("SECURITY ABORT: Test connection is read-only.")

      # Verify database owner is oliver_migrator
      db_owner = conn.execute(
          text("""
                SELECT r.rolname 
                FROM pg_database d 
                JOIN pg_roles r ON d.datdba = r.oid 
                WHERE d.datname = current_database();
            """)
      ).scalar()
      if db_owner != "oliver_migrator":
        raise RuntimeError(
            f"SECURITY ABORT: Database owner is '{db_owner}', expected"
            " 'oliver_migrator'."
        )

      # Verify public schema ownership in oliver_test
      schema_owner = conn.execute(
          text("""
                SELECT r.rolname 
                FROM pg_namespace n 
                JOIN pg_roles r ON n.nspowner = r.oid 
                WHERE n.nspname = 'public';
            """)
      ).scalar()
      if schema_owner != "oliver_test_user":
        raise RuntimeError(
            f"SECURITY ABORT: Public schema owner is '{schema_owner}', expected"
            " 'oliver_test_user'."
        )


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
  """Setup mock AI and disable rate limits for unit test execution."""
  import backend.app.routers.health as hr
  import backend.app.services.ai_provider as aip
  import backend.app.services.chat_service as cs

  mock_p = MockAIProvider()
  cs.ai_provider = mock_p
  hr.ai_provider = mock_p
  aip.ai_provider = mock_p

  # Disable rate limiter during general test execution to avoid artificial 429s
  limiter.enabled = False


@pytest.fixture(autouse=True)
def init_test_db():
  """Create fresh schema for each test function."""
  Base.metadata.create_all(bind=test_engine)
  yield
  Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
  """Provide isolated db session for tests."""
  db = TestingSessionLocal()
  try:
    yield db
  finally:
    db.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
  """Provide FastAPI test client wired with test database session."""

  def override_get_db():
    try:
      yield db_session
    finally:
      pass

  app.dependency_overrides[get_db] = override_get_db
  with TestClient(app) as test_client:
    yield test_client
  app.dependency_overrides.clear()
```

---

## 9. Test Verification Claims & Audit Boundaries

### 9.1 Static Inspection vs Runtime Execution
To maintain absolute compliance with audit integrity standards:
- **Static Inspection Performed:** All 14 tests across [backend/tests/test_auth.py](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/backend/tests/test_auth.py), [backend/tests/test_endpoints.py](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/backend/tests/test_endpoints.py), [backend/tests/test_isolation.py](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/backend/tests/test_isolation.py), and [backend/tests/test_tokens.py](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/backend/tests/test_tokens.py) were read and statically analyzed.
- **Fixture Compatibility Verified:** The structure of `client`, `db_session`, `init_test_db`, and dependency overrides was analyzed against the proposed `conftest.py` and `main.py` lifespan logic.
- **Zero Tests Executed:** **No test commands (`pytest`, `python -m pytest`, or `uvicorn`) were executed during this read-only audit.** Any claim that tests "passed" or "succeeded at runtime" applies solely to historical runs prior to this audit. Stage 2.1A.0 changes will be tested only when implementation is explicitly authorized and performed.

---

## 10. Complete Finding Resolution & Closure Matrix (F-01 through F-10)

| Finding | Topic | Historical Root Cause | Final Stage 2.1A.0 Code Resolution | Closure Status |
|---|---|---|---|---|
| **F-01** | Docker Volume Isolation | Bind mount file permissions on Windows host. | Named volume `postgres_data` with standard UID/GID (999:999). | **RESOLVED (Spec Ready)** |
| **F-02** | Role Initialization & Secrets | Plaintext passwords in repo, non-idempotent scripts. | Idempotent `DO $$` blocks with password alter, restricted ACLs. | **RESOLVED (Spec Ready)** |
| **F-03** | Backup Verification & Snapshots | Unvalidated dumps, concurrency during snapshot. | Dual SHA-256 hashes, 5-table FK referential integrity query. | **RESOLVED (Spec Ready)** |
| **F-04** | Disaster Recovery & Writer Fencing | Ambiguous fencing claims, stale SQLite fallback. | 12-category fencing protocol, active socket probe, strict ban on stale fallback. | **RESOLVED (Spec Ready)** |
| **F-05** | Service Lifecycle | Unbounded restart loops, uncoordinated shutdown. | `stop_grace_period: 30s`, `restart: unless-stopped`, healthcheck waits. | **RESOLVED (Spec Ready)** |
| **F-06** | Least-Privilege Roles | Monolithic roles, missing default privilege locks. | `oliver_migrator` (DDL owner) vs `oliver_app_user` (DML only); default privileges locked. | **RESOLVED (Spec Ready)** |
| **F-07** | Readiness Probes | Unauthenticated ping omitting read-write state. | Authenticated three-tier probe (`tx_ro = 'off'`, table count, migration head). | **RESOLVED (Spec Ready)** |
| **F-08** | Lifespan Fail-Closed Startup | Unconditional `create_all()`, naive dialect check. | Strict dialect + environment + deterministic path gating; Alembic multi-head check. | **RESOLVED (Code Ready for 2.1A.0)** |
| **F-09** | Test Isolation Guard | SQLite path traversal, Win32 trailing dots, unverified engine. | Line 1 pre-import guard, comprehensive Win32 path normalization, independent `app_engine.url` check. | **RESOLVED (Code Ready for 2.1A.0)** |
| **F-10** | Schema Separation | Mixed DDL and DML in application code. | Clean separation: Alembic handles DDL; application code performs only DML. | **RESOLVED (Spec Ready)** |

---

## 11. Final Authorization Assessment

```
================================================================================
FINAL VERDICT: READY FOR STAGE 2.1A.0 IMPLEMENTATION
================================================================================
```

### Scope of Stage 2.1A.0
- **Authorized Files:** Strictly [backend/app/main.py](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/backend/app/main.py) and [backend/tests/conftest.py](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/backend/tests/conftest.py).
- **Prerequisites Required:** Zero new packages, zero Docker daemon access, zero network operations, zero database writes.
- **Unauthorized Stages (2.1A.1 through 2.1A.8):** Remain strictly blocked.

**STOPPING POINT:** This audit task is complete. No implementation has been performed. Await explicit user authorization before applying the changes to `backend/app/main.py` and `backend/tests/conftest.py`.
