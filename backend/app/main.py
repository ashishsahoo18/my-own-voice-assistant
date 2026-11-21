"""Main FastAPI application entry point for OLIVER 3.0 Central Backend."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
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
            logger.info("Development SQLite detected. Initializing schema via create_all()...")
            Base.metadata.create_all(bind=engine)
            return

        # Non-development or unauthorized SQLite target -> Fail closed immediately
        error_msg = (
            f"FATAL STARTUP BLOCKED: create_all() is unauthorized for SQLite target in environment "
            f"'{settings.ENVIRONMENT}'. Auto-DDL is permitted strictly for '{AUTHORIZED_DEV_DB}' "
            "in 'development' mode."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    elif dialect_name in ("postgresql", "postgresql+psycopg"):
        logger.info("PostgreSQL backend detected. Verifying Alembic migration status...")
        script_location = (BACKEND_DIR / "alembic").resolve()

        if not script_location.exists():
            raise RuntimeError(f"FATAL STARTUP BLOCKED: Alembic directory not found at {script_location}")

        script_dir = ScriptDirectory(str(script_location))
        heads = script_dir.get_heads()

        if not heads:
            error_msg = (
                "FATAL STARTUP BLOCKED: No Alembic migrations exist in backend/alembic/versions/. "
                "PostgreSQL requires managed migrations."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        if len(heads) > 1:
            error_msg = (
                f"FATAL STARTUP BLOCKED: Multiple Alembic migration heads detected: {heads}. "
                "Migration branches must be merged via 'alembic merge' before startup."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        expected_head = heads[0]

        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_heads = context.get_current_heads()

        if not current_heads:
            error_msg = (
                "FATAL STARTUP BLOCKED: Database has no applied Alembic revisions (unmigrated). "
                f"Expected migration head: '{expected_head}'."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        if len(current_heads) > 1:
            error_msg = (
                f"FATAL STARTUP BLOCKED: Database contains multiple applied revision heads: {current_heads}."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        current_rev = current_heads[0]
        if current_rev != expected_head:
            error_msg = (
                f"FATAL STARTUP BLOCKED: Database revision '{current_rev}' does not match expected "
                f"Alembic head '{expected_head}'."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        logger.info("Alembic migration head verified successfully: revision %s", current_rev)
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
    logger.info("OLIVER 3.0 Central Backend started successfully on %s:%d", settings.HOST, settings.PORT)
    yield
    logger.info("Shutting down OLIVER 3.0 Central Backend...")


app = FastAPI(
    title="OLIVER 3.0 Central Backend",
    description="Central AI orchestration, authentication, and cross-device sync service for OLIVER.",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
origins = settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if isinstance(origins, list) else [origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing and structured logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000.0
    logger.info(
        "HTTP %s %s - Status: %d - Duration: %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Mount Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(chat_router)
app.include_router(devices_router)
app.include_router(welcome_router)


@app.get("/", tags=["Root"])
def root():
    return {
        "service": "OLIVER 3.0 Central Backend",
        "version": "3.0.0",
        "status": "online",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }
