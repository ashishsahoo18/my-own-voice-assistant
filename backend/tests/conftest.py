"""Pytest configuration and test database fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Generator

import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.database import Base, get_db
from backend.app.core.limiter import limiter
from backend.app.main import app
from backend.app.services.ai_provider import AIProvider

# In-memory test database with StaticPool for thread-safe memory sharing
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
