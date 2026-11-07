"""User profile and preference routes."""

from __future__ import annotations

import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.user import User
from backend.app.schemas.user import UpdatePreferencesRequest, UserProfileResponse

router = APIRouter(prefix="/api/user", tags=["User"])


@router.get("/profile", response_model=UserProfileResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    """Retrieve current authenticated user profile."""
    try:
        prefs = json.loads(current_user.preferences)
    except Exception:
        prefs = {}

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        preferences=prefs,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.patch("/preferences", response_model=UserProfileResponse)
def update_preferences(
    body: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update preferences for the authenticated user."""
    try:
        current_prefs = json.loads(current_user.preferences)
    except Exception:
        current_prefs = {}

    current_prefs.update(body.preferences)
    current_user.preferences = json.dumps(current_prefs)
    db.commit()
    db.refresh(current_user)

    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        preferences=current_prefs,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )

