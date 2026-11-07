"""Main FastAPI application entry point for OLIVER 3.0 Central Backend."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context: initialize database tables and resources."""
    logger.info("Initializing database schema for OLIVER 3.0...")
    # Create tables if not existing (dev SQLite mode)
    Base.metadata.create_all(bind=engine)
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

