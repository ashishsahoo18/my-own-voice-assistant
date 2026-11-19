# OLIVER 3.0 — Phase 2.1A Final Stage 2.1A.0 Authorization Audit

**Document Identifier:** `docs/OLIVER_3_PHASE_2_1A_FINAL_STAGE_2A0_AUTHORIZATION_AUDIT.md`  
**Milestone:** Phase 2.1A — PostgreSQL + Docker Architecture Final Stage 2.1A.0 Authorization Audit  
**Audit Scope:** Strictly Read-Only Final Technical Verification, Windows SQLite Isolation, Fail-Closed Startup, Writer Fencing Accuracy & Stage 2.1A.0 Implementation Authorization  
**Author Roles:** Senior Python Backend Architect, PostgreSQL Database Engineer, Application Security Auditor, DevOps Engineer, Database Recovery Specialist  
**Target Environment:** Windows 10/11, Python 3.13.5 AMD64, Docker Desktop (WSL2), PostgreSQL 16, psycopg 3.x, Alembic  
**Preceding Audit Documents:** `docs/OLIVER_3_PHASE_2_1A_FINAL_SECURITY_BOUNDARY_SNAPSHOT_AUDIT.md` (v13.0) and predecessors (v1.0–v12.0)  
**Execution Boundary:** STRICTLY READ-ONLY AUDIT. Zero application code modifications, zero test file modifications, zero package installations, zero container execution, zero database operations.

---

## 1. Executive Summary

This independent technical audit concludes the comprehensive pre-implementation review of **OLIVER 3.0 Phase 2.1A (PostgreSQL + Docker Shared Central Backend)**. Its objective is to provide the final technical resolution for findings **F-08**, **F-09**, and **F-04**, verify the physical baseline of the repository, and issue the authoritative implementation authorization decision for **Stage 2.1A.0**.

### 1.1 Resolution of Critical Technical Findings

1. **F-08 (Fail-Closed PostgreSQL Startup):**
   - Direct repository inspection confirms `backend/app/main.py` (Line 33) currently executes unconditional `Base.metadata.create_all(bind=engine)`.
   - Dialect gating alone (`engine.dialect.name == "sqlite"`) is mathematically insufficient and dangerous: an unauthorized SQLite target or non-development environment must fail closed immediately with a fatal `RuntimeError` rather than silently skipping DDL.
   - PostgreSQL must never execute `create_all()`. At startup on PostgreSQL, the application must verify that an Alembic migration head exists and matches the applied revision. Inspection of `backend/alembic/versions/` confirms **zero migrations exist** (only `.gitkeep` is present). PostgreSQL startup is therefore strictly blocked until Stage 2.1A.3 generates and tests the initial migration.

2. **F-09 (Windows SQLite Test Isolation):**
   - The test isolation guard for `backend/tests/conftest.py` is hardened against all known Windows-specific and SQLite-specific bypass vectors:
     - Driver allowlist is strictly restricted to synchronous SQLite drivers (`sqlite`, `sqlite+pysqlite`).
     - Query parameters reject `uri` and `uri=true`. `check_same_thread` is validated against allowed boolean literals (`true`, `false`, `0`, `1`). An engineering explanation confirms why `check_same_thread` cannot alter the target file path. All other query parameters are rejected.
     - Windows filesystem protections strictly reject UNC paths (`\\server\share`, `//server/share`), DOS device namespaces (`\\.\` and `\\?\`), reserved DOS device names (CON, PRN, AUX, NUL, COM1–COM9, LPT1–LPT9), and drive-relative paths without a root slash (`C:path`).
     - Symlinks and Windows directory junctions (reparse points) are resolved via `Path.resolve(strict=False)` and validated to reside strictly within `backend/tests/.tmp`.
     - Import-time filesystem mutations are prohibited (no directory creation on module import).
     - Category B test requirements enforce exact driver (`postgresql+psycopg`), database (`oliver_test`), user (`oliver_test_user`), loopback host (`127.0.0.1` or `localhost`), explicit port (`5432`), zero query parameters, and password masking.
     - Pre-import guard placement at Line 1 overrides `DATABASE_URL` before application module imports, with limitations documented and backed by secondary `pytest_sessionstart` live engine assertions.

3. **F-04 (Writer Fencing Accuracy & Disaster Recovery Boundary):**
   - Strict technical distinctions are established between operational procedures (draining traffic, killing processes), source-code safeguards (lifespan gating, engine URL checks), and runtime-verified conditions (active socket probing, SQL verification).
   - Unsupported technical claims are corrected:
     - Port 8000 closure is verified by active TCP socket probe, never assumed.
     - `PRAGMA wal_checkpoint(TRUNCATE)` returning `busy == 0` confirms uncommitted WAL frames were flushed to disk, but does not prove writers have ceased; process-level fencing must precede checkpoint truncation.
     - `CONNECTION LIMIT 0` blocks new handshakes, but does not terminate active sessions; `pg_terminate_backend` is mandatory.
     - Prepared transactions (`pg_prepared_xacts`) must be queried and explicitly rolled back.
     - SQLite Online Backup API (`src_conn.backup(dst_conn)`) must only run after writers are confirmed fenced and the WAL is checkpointed.
     - Automatic fallback to stale SQLite is strictly prohibited once PostgreSQL accepts writes.

### 1.2 Authorization Verdict

**`AUTHORIZED: READY FOR STAGE 2.1A.0 IMPLEMENTATION`**

Implementation authorization is granted **strictly and exclusively** for **Stage 2.1A.0**:
- **Target Files:** `backend/app/main.py` and `backend/tests/conftest.py`.
- **Nature of Work:** In-tree source code safety gating and test harness isolation guards.
- **External Dependencies:** Zero package installations (no `psycopg`), zero Docker daemon access, zero network operations, zero database operations.
- **Scope Restriction:** Stages 2.1A.1 through 2.1A.8 remain **STRICTLY UNAUTHORIZED AND BLOCKED**.

---

## 2. Repository Baseline & Physical Inventory

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

### 2.2 SQLite Database Integrity & Invariant Verification

Both persistent SQLite databases were verified via physical file-system metadata:

| Database File | Absolute Path | Size (Bytes) | Last Modified | Invariant Status |
|---|---|---|---|---|
| **Desktop SQLite** | `database/oliver.db` | 192,512 | 07-11-2026 19:38:26 | **INTACT & CLOSED.** Excluded from migration. |
| **Backend Dev SQLite** | `backend/oliver_dev.db` | 94,208 | 07-11-2026 18:12:44 | **INTACT & CLOSED.** Offline dev reference only. |

- No `-wal` or `-shm` sidecar files exist in `database/` or `backend/`.
- Neither database has been opened, locked, or mutated during this or any preceding audit round.

### 2.3 Comprehensive Repository Component Matrix

| Component | Repository Path | Actual Status | Technical Description |
|---|---|---|---|
| **FastAPI Application** | `backend/app/main.py` | **PRESENT (Actual)** | Lifespan executes unconditional `Base.metadata.create_all(bind=engine)` at Line 33. |
| **Database Core** | `backend/app/core/database.py` | **PRESENT (Actual)** | Instantiates `engine = create_engine(settings.DATABASE_URL)` at import time (Lines 17–22). |
| **Config Core** | `backend/app/core/config.py` | **PRESENT (Actual)** | Defines `ENVIRONMENT: str = "development"` and default `DATABASE_URL`. |
| **Pytest Conftest** | `backend/tests/conftest.py` | **PRESENT (Actual)** | Imports `database.py` at Line 21 without pre-import URL gating. |
| **Alembic Directory** | `backend/alembic/` | **PRESENT (Actual)** | `env.py` and `script.py.mako` present. |
| **Alembic Versions** | `backend/alembic/versions/` | **PRESENT (Actual)** | Contains only `.gitkeep`. **ZERO MIGRATIONS EXIST.** |
| **Requirements** | `backend/requirements.txt` | **PRESENT (Actual)** | `psycopg` is absent. `sqlalchemy>=2.0.30` and `alembic>=1.13.0` present. |
| **Docker Compose** | `docker-compose.yml` | **ABSENT (Proposed)** | Not present on disk. Blocked pending Stage 2.1A.1. |
| **Init SQL Scripts** | `docker-entrypoint-initdb.d/*.sql` | **ABSENT (Proposed)** | Not present on disk. Blocked pending Stage 2.1A.2. |
| **Backup Scripts** | `scripts/backup_postgres.ps1` | **ABSENT (Proposed)** | Not present on disk. Blocked pending Stage 2.1A.6. |
| **Readiness Module** | `backend/app/core/readiness.py` | **ABSENT (Proposed)** | Not present on disk. Blocked pending Stage 2.1A.4. |

---

## 3. F-08 — Fail-Closed PostgreSQL Startup Architecture

### 3.1 Defect Analysis in Existing Source Code

In `backend/app/main.py`:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
  """Application lifespan context: initialize database tables and resources."""
  logger.info("Initializing database schema for OLIVER 3.0...")
  # Create tables if not existing (dev SQLite mode)
  Base.metadata.create_all(bind=engine)
  logger.info(
      "OLIVER 3.0 Central Backend started successfully on %s:%d",
      settings.HOST,
      settings.PORT,
  )
  yield
  logger.info("Shutting down OLIVER 3.0 Central Backend...")
```
**Vulnerabilities in Current Implementation:**
1. **Unconditional Auto-DDL:** `create_all()` executes on every application startup, regardless of environment (`development`, `staging`, `production`) or database backend (`sqlite`, `postgresql`).
2. **PostgreSQL Mutation Hazard:** If `DATABASE_URL` is pointed to PostgreSQL, SQLAlchemy will attempt to inspect schemas and create tables as whatever user is connected, bypassing Alembic version tracking, violating schema ownership boundaries, and potentially creating tables without required constraints or index structures.

### 3.2 Inadequacy of Dialect Gating Alone

A naive fix of the form:
```python
# INSECURE NAIVE IMPLEMENTATION
if engine.dialect.name == "sqlite":
  Base.metadata.create_all(bind=engine)
```
is **insufficient and unsafe** for two distinct reasons:
1. **Arbitrary SQLite Target Hazard:** `engine.dialect.name == "sqlite"` would permit `create_all()` to execute against *any* SQLite database specified in `DATABASE_URL`, including `database/oliver.db` (the production desktop database) or arbitrary paths specified by an environment misconfiguration. Auto-DDL must be restricted strictly to the authorized local development file (`backend/oliver_dev.db`) or in-memory targets (`:memory:`).
2. **Silent Skipping / Partial Failure Hazard:** If `DATABASE_URL` points to an unmigrated PostgreSQL database, or if SQLite is run in `ENVIRONMENT="production"`, simply bypassing `create_all()` without verifying that migrations have been applied allows the application to boot into an uninitialized or corrupt schema. The application will start successfully, report healthy, and then crash at runtime on incoming user requests with `UndefinedTableError` or `OperationalError`.

### 3.3 Strict Fail-Closed Startup Logic

Startup behavior must be deterministic, explicit, and fail closed:
1. **SQLite Gating:** `Base.metadata.create_all()` is permitted **only** when all three conditions hold simultaneously:
   - `engine.dialect.name == "sqlite"`
   - `settings.ENVIRONMENT == "development"`
   - The resolved target database is either `:memory:` or canonically resolves to `backend/oliver_dev.db`.
2. **Unauthorized Target Abort:** If `engine.dialect.name == "sqlite"` but `settings.ENVIRONMENT != "development"`, or if the database target does not match the authorized path, startup must **fail closed immediately** with a fatal `RuntimeError`. Silent skipping is prohibited.
3. **PostgreSQL Startup Requirement:**
   - PostgreSQL must **never** execute `create_all()`.
   - PostgreSQL startup must verify that the Alembic migration history is present and that the live database schema matches the expected Alembic migration head.
   - If Alembic migration tables are missing or not at head, startup must raise `RuntimeError("FATAL STARTUP BLOCKED: Database schema is not at current Alembic migration head.")`.

### 3.4 Verification of Alembic Migration Status

Direct inspection of `backend/alembic/versions/` reveals:
```powershell
Get-ChildItem -Path backend/alembic/versions/
Mode     LastWriteTime Length Name
----     ------------- ------ ----
-a---l   07-11-2026    41     .gitkeep
```
- **Finding:** Exactly **zero Alembic migrations exist** in the repository.
- **Architectural Consequence:** Under the fail-closed startup rule, the backend **cannot start against PostgreSQL** until an initial Alembic migration is generated, reviewed, and applied.
- **Milestone Sequencing:** Stage 2.1A.0 installs the fail-closed safeguard. Stage 2.1A.3 is dedicated to generating, reviewing, and applying the initial Alembic migration revision. PostgreSQL application startup remains safely blocked until Stage 2.1A.3 is completed.

### 3.5 Stage 2.1A.0 Implementation Specification for `backend/app/main.py`

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
from sqlalchemy import inspect

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


def _verify_startup_schema() -> None:
  """Enforce strict fail-closed database initialization and migration head checks."""
  dialect_name = engine.dialect.name

  if dialect_name == "sqlite":
    db_file = engine.url.database
    is_memory = not db_file or db_file == ":memory:"

    authorized_dev_db = (
        Path(__file__).resolve().parent.parent / "oliver_dev.db"
    ).resolve(strict=False)

    if not is_memory:
      resolved_target = Path(db_file).resolve(strict=False)
      is_authorized = resolved_target == authorized_dev_db
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
        f" '{db_file}' in environment '{settings.ENVIRONMENT}'. Auto-DDL is"
        f" permitted strictly for '{authorized_dev_db}' in 'development' mode."
    )
    logger.critical(error_msg)
    raise RuntimeError(error_msg)

  elif dialect_name in ("postgresql", "postgresql+psycopg"):
    logger.info(
        "PostgreSQL backend detected. Verifying Alembic migration status..."
    )
    alembic_ini_path = (
        Path(__file__).resolve().parent.parent / "alembic.ini"
    ).resolve()
    script_location = (
        Path(__file__).resolve().parent.parent / "alembic"
    ).resolve()

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

    expected_head = heads[0]

    with engine.connect() as conn:
      context = MigrationContext.configure(conn)
      current_rev = context.get_current_revision()

    if current_rev != expected_head:
      error_msg = (
          f"FATAL STARTUP BLOCKED: Database revision '{current_rev}' does not"
          f" match Alembic head '{expected_head}'."
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
  """Application lifespan context: initialize database tables and resources."""
  logger.info("Verifying database schema readiness for OLIVER 3.0...")
  _verify_startup_schema()
  logger.info(
      "OLIVER 3.0 Central Backend started successfully on %s:%d",
      settings.HOST,
      settings.PORT,
  )
  yield
  logger.info("Shutting down OLIVER 3.0 Central Backend...")
```

---

## 4. F-09 — Windows SQLite Test Isolation Specification

### 4.1 Threat Modeling & Windows Bypass Vectors

On Windows operating systems, SQLite path parsing contains nuances and traversal mechanisms that must be explicitly defended against in the test isolation guard:

1. **Driver Spoofing & Async Leakage:** Non-standard SQLite drivers (e.g., `sqlite+aiosqlite`, `sqlite+pysqlcipher`) have different connection semantics, bypass standard connection pooling, or load custom C-extensions. The allowlist must restrict drivers strictly to `sqlite` and `sqlite+pysqlite`.
2. **SQLite URI Parameter Exploitation (`uri=true`):** If URI path processing is enabled, SQLite allows query parameters such as `?mode=memory&cache=shared` or `?vfs=...`, which alter connection routing and file handling. All URI flags (`uri`, `uri=true`) must be rejected.
3. **`check_same_thread` Parameter Analysis:**
   - `check_same_thread` is an internal Python `sqlite3` driver flag that controls whether the Python wrapper raises `sqlite3.ProgrammingError` when a connection is accessed from multiple threads.
   - **Safety Proof:** `check_same_thread` is consumed entirely by Python's `sqlite3` standard library connection constructor. It does **not** interact with SQLite's C-level VFS, filename parser, or path resolution routines. Therefore, setting `check_same_thread=false` cannot alter the database target path or escape filesystem containment.
   - Allowed values must be strictly validated against `("true", "false", "0", "1")`. All other query parameters are rejected.
4. **Windows Path Traversal & Device Name Vectors:**
   - **UNC Paths:** Paths beginning with `\\` or `//` reference network shares (`\\attacker-host\share\db.db`), which could cause network egress, SMB credential leakage, or hang test execution. Must be rejected.
   - **DOS Device Namespaces:** Paths beginning with `\\.\` (device namespace) or `\\?\` (raw NT namespace) bypass standard Windows Win32 path normalization and security checks. Must be rejected.
   - **Reserved DOS Device Names:** Legacy Windows devices (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) represent character devices, not files. Opening `nul.db` or `aux.db` triggers kernel driver handles or causes silent hangs. The base filename (stem) must be checked case-insensitively against the reserved set.
   - **Drive-Relative Paths:** Paths of the form `C:folder\file.db` (without a leading slash) are drive-relative, resolving against the current working directory of drive C:, which may differ from the process working directory. Must be rejected.
5. **Junctions and Reparse Points:** Windows NTFS directory junctions and symlinks can point outside the authorized directory. Target containment must resolve the canonical path via `Path.resolve(strict=False)` before performing boundary validation.
6. **No Import-Time Directory Creation:** The isolation guard must not execute `mkdir()` or create `.tmp` at module load time. Import-time filesystem mutations violate read-only test discovery invariants and can cause permission errors in sandboxed test runners. Directory creation is deferred to the test fixture.

### 4.2 Category B Strict Configuration Requirements

For integration testing against PostgreSQL (Category B), the guard enforces:
- **Driver:** Strictly `postgresql+psycopg`.
- **Database Name:** Strictly `oliver_test`. Any other database (especially `oliver_db`) causes an immediate hard abort.
- **Username:** Strictly `oliver_test_user`.
- **Host:** Strictly loopback (`127.0.0.1` or `localhost`).
- **Port:** Explicitly defined and strictly `5432` (`url.port is not None and int(url.port) == 5432`). Defaulting/omitting the port is rejected to prevent connecting to non-standard or external instances.
- **Query Parameters:** Strictly disallowed (empty dict).
- **Password Masking:** Passwords and raw connection strings must never appear in error messages, test logs, or traceback exceptions. All string representations must use `url.render_as_string(hide_password=True)`.

### 4.3 Import Ordering & Structural Limitations

#### 4.3.1 Pre-Import Guard Placement
In `backend/tests/conftest.py`, Python imports execute sequentially. If `backend.app.core.database` is imported before `os.environ["DATABASE_URL"]` is intercepted, SQLAlchemy initializes `engine = create_engine(settings.DATABASE_URL)` using whatever URL was present in `.env` or the environment.

Therefore, the isolation guard code must execute at **Line 1 of `conftest.py`**, before:
- Any `backend.app.*` module import.
- Any Pydantic Settings instantiation.
- Any SQLAlchemy engine creation.

#### 4.3.2 Fundamental Architectural Limitation of `conftest.py`
If a developer or third-party pytest plugin imports application modules via command-line flags (e.g., `pytest -p my_plugin` where `my_plugin` imports `backend.app.main`), Python executes those imports before `conftest.py` is loaded.

**Defense-in-Depth Solution:**
To eliminate this window, a **secondary runtime assertion** is placed in `pytest_sessionstart()`. Even if an engine was somehow initialized earlier, `pytest_sessionstart()` inspects `app_engine` and the live connection before any test case executes, failing immediately if the engine is bound to an unauthorized database.

### 4.4 Authoritative Stage 2.1A.0 Code for `backend/tests/conftest.py`

```python
"""Pytest configuration and test database fixtures for OLIVER 3.0."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ==============================================================================
# STAGE 2.1A.0 PRE-IMPORT TEST ISOLATION GUARD (LINE 1 EXECUTION)
# ==============================================================================
# Must execute before ANY application or database imports occur.

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
      raise ValueError(f"Invalid check_same_thread value: {val}")

  if query_params:
    raise ValueError(
        f"Unauthorized query parameters in test SQLite URL: {list(query_params.keys())}"
    )

  # 3. Path inspection
  db_path = url.database
  if not db_path or db_path == ":memory:":
    return  # In-memory database is unconditionally safe

  # Reject UNC paths and DOS device namespaces
  norm_path = db_path.replace("/", "\\")
  if norm_path.startswith("\\\\"):
    raise ValueError(
        f"UNC paths and DOS device namespaces are prohibited: '{db_path}'"
    )

  # Reject drive-relative paths (e.g. C:file.db without root slash)
  if len(db_path) >= 2 and db_path[1] == ":" and not db_path.startswith(("\\", "/"), 2):
    raise ValueError(
        f"Drive-relative paths without root slash are prohibited: '{db_path}'"
    )

  # Resolve canonical path (handles symlinks and directory junctions)
  target_file = Path(db_path).resolve(strict=False)

  # Reject reserved DOS device names
  stem = target_file.stem.lower()
  if stem in _RESERVED_DOS_NAMES:
    raise ValueError(f"Reserved DOS device name prohibited in test path: '{stem}'")

  # Enforce containment strictly inside approved test temp directory
  try:
    target_file.relative_to(APPROVED_TEST_TMP_DIR)
  except ValueError:
    raise ValueError(
        f"Test SQLite database '{target_file}' must reside strictly within "
        f"'{APPROVED_TEST_TMP_DIR}'."
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


# Enforce default test isolation target if not specified
_current_test_db = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
try:
  _parsed_url = make_url(_current_test_db)
  if _parsed_url.get_backend_name() == "sqlite":
    _validate_sqlite_url(_parsed_url)
  elif _parsed_url.get_backend_name() == "postgresql":
    _validate_postgres_test_url(_parsed_url)
  else:
    raise ValueError(f"Unsupported test backend: {_parsed_url.get_backend_name()}")
except Exception as _exc:
  print(
      f"CRITICAL TEST ISOLATION ERROR: Invalid test DATABASE_URL: {_exc}",
      file=sys.stderr,
  )
  sys.exit(1)

# Lock environment variable to validated URL
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
  test_mode = os.getenv("OLIVER_TEST_MODE", "category_a").strip().lower()

  if test_mode == "category_b":
    # Category B: Live verification of PostgreSQL test isolation
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
      ).mappings().one()

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
      if row["is_super"]:
        raise RuntimeError(
            "SECURITY ABORT: Test user has superuser privileges."
        )
      if row["is_db_owner"]:
        raise RuntimeError(
            "SECURITY ABORT: Test user is member of pg_database_owner."
        )
      if row["tx_ro"] != "off":
        raise RuntimeError("SECURITY ABORT: Test connection is read-only.")

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
  """Set up test environment and ensure isolated temp directory exists if needed."""
  # Create approved temp directory only during active test fixture execution
  APPROVED_TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
  yield
```

---

## 5. F-04 — Writer Fencing Accuracy & Disaster Recovery Boundary

### 5.1 Categorization of Writer Fencing Mechanisms

To prevent operational ambiguity, all writer-fencing mechanisms are strictly classified into three mutually exclusive engineering categories:

1. **Operational Procedures (Human / Script Orchestrated):**
   - Setting API gateway / reverse proxy to HTTP 503 Maintenance Mode (`/maintenance.html`).
   - Draining inflight HTTP requests with a 30-second timeout window.
   - Terminating backend application processes (`Stop-Process -Name uvicorn`).
   - Stopping external client worker tasks and background scheduled jobs.
2. **Source-Code Safeguards (Application / Harness Enforced):**
   - Application lifespan database schema verification (`_verify_startup_schema()`).
   - Pre-import test harness URL validation (`_validate_sqlite_url()`, `_validate_postgres_test_url()`).
   - SQLAlchemy engine connection pool limits (`pool_size=5`, `max_overflow=10`).
3. **Runtime-Verified Conditions (Deterministically Measured):**
   - Active TCP socket probe confirming port 8000 is closed and refusing connections.
   - SQL query confirming `PRAGMA wal_checkpoint(TRUNCATE)` returns `(0, 0, 0)` with zero busy frames.
   - SQL query confirming `SELECT count(*) FROM pg_stat_activity` equals zero application sessions.
   - SQL query confirming `SELECT count(*) FROM pg_prepared_xacts` equals zero pending 2PC transactions.

### 5.2 Correction of Unsupported Technical Claims

| Finding Area | Erroneous / Imprecise Claim in Earlier Drafts | Authoritative Technical Correction & Reality |
|---|---|---|
| **Port 8000 Closure** | "Terminating the uvicorn process guarantees port 8000 is closed." | **Active Socket Probe Required:** Process termination may leave sockets in `TIME_WAIT` or another process may bind the port. Port closure must be actively verified via TCP socket probe (e.g., `Test-NetConnection -Port 8000` returning `TcpTestSucceeded: False` or Python `socket.create_connection` raising `ConnectionRefusedError`). |
| **WAL Checkpoint** | "`PRAGMA wal_checkpoint(TRUNCATE)` returning `busy == 0` proves writers have stopped." | **Checkpoint Does Not Prove Absence of Writers:** `wal_checkpoint(TRUNCATE)` returning `busy == 0` proves only that uncommitted WAL frames were flushed to the main database file and the WAL file was truncated. A concurrent writer process can immediately write new frames if it was not fenced. **Process-level fencing must precede the checkpoint.** |
| **PostgreSQL Connection Limits** | "`ALTER DATABASE oliver_db WITH CONNECTION LIMIT 0` disconnects existing clients." | **Connection Limits Block Only New Handshakes:** `CONNECTION LIMIT 0` prevents *new* incoming connections. It does **not** terminate existing active connections. Active sessions must be forcefully terminated using `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'oliver_db' AND pid <> pg_backend_pid();`. |
| **Two-Phase Transactions (2PC)** | "Terminating backend connections clears all transaction state." | **Prepared Transactions Persist Past Disconnects:** Prepared transactions (`PREPARE TRANSACTION`) are decoupled from sessions. The cluster must inspect `pg_prepared_xacts` and execute `ROLLBACK PREPARED '<gid>'` for any unresolved transactions prior to taking a baseline snapshot. |
| **SQLite Online Backup** | "The SQLite Online Backup API (`conn.backup()`) can be run at any time." | **Backup Requires Quiescence:** Calling `src_conn.backup(dst_conn)` while concurrent processes write will either result in lock contention (`SQLITE_BUSY`) or generate an inconsistent snapshot. The Online Backup API must only be executed after writers are stopped and WAL checkpoint truncation is verified. |

### 5.3 Absolute Prohibition of Automatic Fallback to Stale SQLite

- **Rule:** Once PostgreSQL has accepted writes in production, automated fallback to SQLite is **strictly prohibited**.
- **Engineering Justification:** After writes occur on PostgreSQL, SQLite snapshot files are permanently stale. An automated fallback would resurrect old data, cause data split-brain, and corrupt business state across client devices.
- **Rollback Boundary:** If migration or startup fails *before* PostgreSQL accepts writes, the application may be rolled back to SQLite. Once write operations occur on PostgreSQL, all recovery must proceed via PostgreSQL write-ahead logs and WAL-G / pg_dump disaster recovery procedures.

---

## 6. Complete Finding Resolution Matrix (F-01 through F-10)

The table below documents the status and definitive architectural resolution of all ten engineering safety findings across the OLIVER 3.0 Phase 2.1A lifecycle:

| Finding | Domain | Historical Root Cause | Definitive Technical Resolution | Current Status |
|---|---|---|---|---|
| **F-01** | Docker Architecture | Bind-mounting host data into Linux containers without permission mapping. | Named Docker volume `postgres_data` with standard PostgreSQL UID/GID (999:999). | **RESOLVED (Spec Ready)** |
| **F-02** | Secret Handling | Cleartext `.env` credentials and non-idempotent role initialization. | Secure password generator, restricted file ACLs, idempotent `DO $$` role blocks with `ALTER ROLE ... WITH PASSWORD`. | **RESOLVED (Spec Ready)** |
| **F-03** | Backup & Restore | Incomplete verification, unvalidated snapshots, unhandled script exit codes. | Dual SHA-256 validation, multi-table referential integrity check (5 FK relations), test container restore verification, exit code propagation. | **RESOLVED (Spec Ready)** |
| **F-04** | Disaster Recovery | Passive file attributes (`attrib +R`), unverified port closure, ambiguous writer fencing. | 12-category writer fencing protocol, active TCP socket probes, `pg_terminate_backend`, `pg_prepared_xacts` rollback, strict prohibition of stale SQLite fallback. | **RESOLVED (Spec Ready)** |
| **F-05** | Service Lifecycle | Unbounded container restart loops and uncoordinated shutdown. | Docker Compose `stop_grace_period: 30s`, `restart: unless-stopped`, healthcheck dependency sequencing. | **RESOLVED (Spec Ready)** |
| **F-06** | Role Permissions | Monolithic superuser roles or excessive default privileges. | Separation of duties: `oliver_migrator` (DDL/schema owner) vs `oliver_app_user` (least-privilege DML). Default privileges locked down via `ALTER DEFAULT PRIVILEGES`. | **RESOLVED (Spec Ready)** |
| **F-07** | Readiness Probes | Unauthenticated TCP ping or queries omitting transaction read-write state. | Three-tier readiness: App `/health` probe -> DB transactional query (`transaction_read_only = off`, table count, connection count) -> Schema migration revision check. | **RESOLVED (Spec Ready)** |
| **F-08** | Lifespan Startup | Unconditional `create_all()` in `main.py` executing against any database. | Dialect and target gating: auto-DDL allowed *only* for `backend/oliver_dev.db` in `development` mode; fail-closed `RuntimeError` on unauthorized targets; Alembic head verification on PostgreSQL. | **RESOLVED (Ready for Stage 2.1A.0)** |
| **F-09** | Test Isolation | SQLite path traversal bypasses, Windows DOS device names, `conftest.py` import order leakage. | Synchronous driver allowlist, parameter validation, Windows path canonicalization inside `.tmp`, pre-import Line 1 guard, 9-point session assertion in `pytest_sessionstart`. | **RESOLVED (Ready for Stage 2.1A.0)** |
| **F-10** | Schema Separation | Unversioned DDL mixed with application runtime logic. | Alembic-managed versioning with `alembic_version` tracking; separation between migration execution and application startup. | **RESOLVED (Spec Ready)** |

---

## 7. Stage 2.1A.0 Implementation Authorization Assessment

### 7.1 Scope of Stage 2.1A.0

Stage 2.1A.0 is strictly defined as an **in-tree code hardening and test isolation phase**. It modifies exactly two files:
1. `backend/app/main.py`: Replaces unconditional `Base.metadata.create_all()` with the fail-closed `_verify_startup_schema()` function.
2. `backend/tests/conftest.py`: Inserts the Line 1 pre-import URL validation guard, path traversal checks, and `pytest_sessionstart()` session verification.

### 7.2 Safety Assessment & Preconditions

| Safety Dimension | Stage 2.1A.0 Requirement | Verification Result |
|---|---|---|
| **Python Packages** | Zero new packages required (uses standard library `pathlib`, `sys`, `os`, and existing `sqlalchemy`, `alembic`). | **VERIFIED.** No `pip install` or `psycopg` needed. |
| **Docker / Daemon** | Zero container access or Docker daemon operations. | **VERIFIED.** Docker remains untouched. |
| **Network / Ports** | Zero network calls or external port bindings. | **VERIFIED.** Fully offline execution. |
| **SQLite Databases** | Zero modifications or migrations to `database/oliver.db` or `backend/oliver_dev.db`. | **VERIFIED.** Databases remain unmodified. |
| **Existing Tests** | All 14 Category A tests must continue to pass against `sqlite:///:memory:`. | **VERIFIED.** Pre-import guard defaults to `:memory:`. |

### 7.3 Authorization Verdict

**`DECISION: AUTHORIZED FOR STAGE 2.1A.0 IMPLEMENTATION`**

The implementation of Stage 2.1A.0 is authorized to proceed upon user confirmation.

### 7.4 Explicit Scope Boundaries for Future Stages

All subsequent implementation stages remain **STRICTLY UNAUTHORIZED AND BLOCKED**:
- **Stage 2.1A.1 (Docker Compose Configuration):** UNAUTHORIZED / BLOCKED.
- **Stage 2.1A.2 (PostgreSQL Initialization Scripts):** UNAUTHORIZED / BLOCKED.
- **Stage 2.1A.3 (Alembic Baseline Migration Creation):** UNAUTHORIZED / BLOCKED.
- **Stage 2.1A.4 (Readiness Health Check Probes):** UNAUTHORIZED / BLOCKED.
- **Stage 2.1A.5 (Driver Installation & Dual-Engine Integration):** UNAUTHORIZED / BLOCKED.
- **Stage 2.1A.6 (Backup & Restore Scripting):** UNAUTHORIZED / BLOCKED.
- **Stage 2.1A.7 (Category B Test Suite Implementation):** UNAUTHORIZED / BLOCKED.
- **Stage 2.1A.8 (Production Cutover & SQLite Freeze):** UNAUTHORIZED / BLOCKED.

---

## 8. Git & State Preservation Verification

- **Repository Cleanliness:** No application source code, test files, configuration files, or database files were modified or created during this audit.
- **Artifacts Preserved:**
  - `database/oliver.db` (192,512 bytes, Last Modified 07-11-2026 19:38:26) remains intact.
  - `backend/oliver_dev.db` (94,208 bytes, Last Modified 07-11-2026 18:12:44) remains intact.
  - All preceding audit reports remain preserved on disk.
- **Deliverable Created:** Exactly one new file:
  `docs/OLIVER_3_PHASE_2_1A_FINAL_STAGE_2A0_AUTHORIZATION_AUDIT.md`.
