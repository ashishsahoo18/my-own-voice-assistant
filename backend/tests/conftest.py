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

APPROVED_TEST_TMP_DIR = (PROJECT_ROOT / "backend" / "tests" / ".tmp").resolve()


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
        raise ValueError("URL-encoded characters are prohibited in SQLite test database paths.")

    # Reject NTFS Alternate Data Streams (colon beyond drive letter index 1)
    after_drive = raw_path[2:] if (len(raw_path) >= 2 and raw_path[1] == ":") else raw_path
    if ":" in after_drive:
        raise ValueError("NTFS Alternate Data Streams (':') are prohibited in test database paths.")

    # Reject trailing dots and spaces in ANY path component (Windows Win32 bypass)
    path_obj = Path(raw_path)
    for part in path_obj.parts:
        if part not in ("\\", "/") and part.endswith((".", " ")):
            raise ValueError(
                f"Path components with trailing dots or spaces are prohibited on Windows: '{part}'."
            )

    # Reject UNC paths and DOS device namespaces
    norm_path = raw_path.replace("/", "\\")
    if norm_path.startswith("\\\\"):
        raise ValueError("UNC paths and DOS device namespaces (\\\\.\\, \\\\?\\) are prohibited.")

    # Reject drive-relative paths (e.g. C:file.db without root slash)
    if (
        len(raw_path) >= 2
        and raw_path[1] == ":"
        and not (len(raw_path) > 2 and raw_path[2] in ("\\", "/"))
    ):
        raise ValueError("Drive-relative paths without a root directory separator are prohibited.")

    # Reject reserved DOS device names in any component
    for part in path_obj.parts:
        stem = part.split(".")[0].lower()
        if stem in _RESERVED_DOS_NAMES:
            raise ValueError(f"Reserved DOS device name prohibited in path component: '{stem}'.")

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
            f"Test SQLite database path must reside strictly within '{APPROVED_TEST_TMP_DIR}'."
        )

    if target_file == APPROVED_TEST_TMP_DIR:
        raise ValueError("Test SQLite database path cannot be the .tmp directory itself.")


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
        "CRITICAL TEST ISOLATION ERROR: OLIVER_TEST_MODE environment variable is not set. "
        "You must explicitly configure OLIVER_TEST_MODE='category_a' (for SQLite unit tests) "
        "or OLIVER_TEST_MODE='category_b' (for PostgreSQL integration tests).",
        file=sys.stderr,
    )
    sys.exit(1)

_test_mode = _raw_mode.strip().lower()
if _test_mode not in ("category_a", "category_b"):
    print(
        f"CRITICAL TEST ISOLATION ERROR: Invalid OLIVER_TEST_MODE '{_test_mode}'. "
        "Allowed values: 'category_a', 'category_b'.",
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
                "Contradictory test configuration: SQLite database URL specified, "
                f"but OLIVER_TEST_MODE is '{_test_mode}'. Expected 'category_a'."
            )
        _validate_sqlite_url(_parsed_url)
    elif _backend_name == "postgresql":
        if _test_mode != "category_b":
            raise ValueError(
                "Contradictory test configuration: PostgreSQL database URL specified, "
                f"but OLIVER_TEST_MODE is '{_test_mode}'. Expected 'category_b'."
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
        "CRITICAL TEST ISOLATION ERROR: Database connection URL is malformed, "
        "contains invalid syntax, or failed parsing.",
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
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


class MockAIProvider(AIProvider):
    """Mock AI Provider for deterministic test execution."""

    async def generate_response(self, prompt: str, system_prompt: str = "") -> tuple[str, float]:
        clean = prompt.strip().lower()
        if "hello" in clean or "hi" in clean:
            return "Hello! I am OLIVER, your personal AI assistant. How can I help you today?", 1.0
        return f"Mock AI answer to: {prompt}", 15.0

    async def check_health(self) -> tuple[bool, str, str]:
        return True, "mock-llama3.2", ""


def pytest_sessionstart(session):
    """Secondary live defense: verify engine and database connection identity before test run."""
    # 1. Verify test mode invariant
    current_env_mode = os.environ.get("OLIVER_TEST_MODE", "").strip().lower()
    if current_env_mode != _EXPECTED_TEST_MODE:
        raise RuntimeError(
            "SECURITY ABORT: OLIVER_TEST_MODE was tampered with after initial guard. "
            f"Expected '{_EXPECTED_TEST_MODE}', got '{current_env_mode}'."
        )

    # 2. Independently validate the actual app_engine.url
    actual_url = app_engine.url
    actual_backend = actual_url.get_backend_name()

    if _EXPECTED_TEST_MODE == "category_a":
        if actual_backend != "sqlite":
            raise RuntimeError(
                f"SECURITY ABORT: Category A test runner detected non-SQLite application engine dialect: '{actual_backend}'."
            )

        _validate_sqlite_url(actual_url)

        expected_db = _EXPECTED_TEST_URL_OBJECT.database
        actual_db = actual_url.database

        is_expected_mem = not expected_db or expected_db == ":memory:"
        is_actual_mem = not actual_db or actual_db == ":memory:"

        if is_expected_mem != is_actual_mem:
            raise RuntimeError(
                "SECURITY ABORT: Engine database target mismatch between expected and actual in-memory status."
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
                    "SECURITY ABORT: Engine database file path mismatch between expected and actual target."
                )

    elif _EXPECTED_TEST_MODE == "category_b":
        if actual_backend != "postgresql":
            raise RuntimeError(
                f"SECURITY ABORT: Category B test runner detected non-PostgreSQL application engine dialect: '{actual_backend}'."
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
                "SECURITY ABORT: Category B application engine URL parameters do not match strict isolation baseline."
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
                raise RuntimeError("SECURITY ABORT: Failed to retrieve user identity from pg_user.")

            if row["curr_db"] != "oliver_test":
                raise RuntimeError(
                    f"SECURITY ABORT: Connected to database '{row['curr_db']}' instead of 'oliver_test'."
                )
            if row["curr_user"] != "oliver_test_user":
                raise RuntimeError(
                    f"SECURITY ABORT: Connected as user '{row['curr_user']}' instead of 'oliver_test_user'."
                )
            if row["sess_user"] != "oliver_test_user":
                raise RuntimeError(
                    f"SECURITY ABORT: Session user is '{row['sess_user']}' instead of 'oliver_test_user'."
                )
            if bool(row["is_super"]):
                raise RuntimeError("SECURITY ABORT: Test user has superuser privileges.")
            if bool(row["is_db_owner"]):
                raise RuntimeError("SECURITY ABORT: Test user is member of pg_database_owner.")
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
                    f"SECURITY ABORT: Database owner is '{db_owner}', expected 'oliver_migrator'."
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
                    f"SECURITY ABORT: Public schema owner is '{schema_owner}', expected 'oliver_test_user'."
                )


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup mock AI and disable rate limits for unit test execution."""
    import backend.app.services.chat_service as cs
    import backend.app.routers.health as hr
    import backend.app.services.ai_provider as aip

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
