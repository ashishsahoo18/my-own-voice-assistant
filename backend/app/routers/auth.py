"""Authentication routes: registration, login, refresh, and logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.limiter import limiter
from backend.app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from backend.app.schemas.user import UserProfileResponse
from backend.app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user and return initial access + refresh tokens."""
    user = AuthService.register_user(db, body)
    return AuthService.create_user_tokens(db, user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email and password and return access + refresh tokens."""
    user = AuthService.authenticate_user(db, body)
    return AuthService.create_user_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Rotate an existing valid refresh token and receive a fresh token pair."""
    return AuthService.rotate_refresh_token(db, body.refresh_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(body: LogoutRequest, db: Session = Depends(get_db)):
    """Revoke a refresh token on logout."""
    AuthService.revoke_refresh_token(db, body.refresh_token)
    return {"message": "Logged out successfully."}

