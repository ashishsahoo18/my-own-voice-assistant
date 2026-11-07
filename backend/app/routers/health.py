"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.schemas.common import HealthResponse
from backend.app.services.ai_provider import ai_provider

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """System health check endpoint verifying database connectivity and AI inference status."""
    # Check DB
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"unhealthy ({type(exc).__name__})"

    # Check Ollama
    is_healthy, model, err = await ai_provider.check_health()
    ollama_status = "online" if is_healthy else f"offline: {err}"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        version="3.0.0",
        environment=settings.ENVIRONMENT,
        database=db_status,
        ollama_status=ollama_status,
        ollama_model=model,
    )

