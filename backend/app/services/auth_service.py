"""Authentication business logic: registration, login, token rotation, and revocation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from backend.app.models.token import RefreshToken
from backend.app.models.user import User
from backend.app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


class AuthService:
    """Manages secure registration, credential verification, and rotating token lifecycles."""

    @staticmethod
    def register_user(db: Session, req: RegisterRequest) -> User:
        """Register a new user with hashed password and unique email constraint."""
        existing = db.execute(select(User).where(User.email == req.email.lower())).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email address is already registered.",
            )

        user = User(
            email=req.email.lower(),
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
            preferences=json.dumps({"theme": "dark", "voice_enabled": True, "language": "en"}),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, req: LoginRequest) -> User:
        """Authenticate user by email and password."""
        user = db.execute(select(User).where(User.email == req.email.lower())).scalar_one_or_none()
        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This user account is inactive.",
            )
        return user

    @staticmethod
    def create_user_tokens(db: Session, user: User) -> TokenResponse:
        """Issue access token and persist a cryptographically hashed, rotating refresh token."""
        access_token = create_access_token(
            subject=user.id,
            claims={"email": user.email, "name": user.full_name},
        )
        raw_refresh = generate_refresh_token()
        token_hash = hash_token(raw_refresh)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        db_token = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked=False,
        )
        db.add(db_token)
        db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    def rotate_refresh_token(db: Session, raw_refresh_token: str) -> TokenResponse:
        """Rotate refresh token: revoke current token and issue a fresh token pair."""
        token_hash = hash_token(raw_refresh_token)
        db_token = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token.",
            )

        if db_token.revoked:
            # Token reuse detected! Revoke all tokens for this user for security
            db.query(RefreshToken).filter(RefreshToken.user_id == db_token.user_id).update({"revoked": True})
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token reuse detected. Session terminated for security.",
            )

        # Check expiration
        now = datetime.now(timezone.utc)
        if db_token.expires_at.tzinfo is None:
            # Handle naive datetime from sqlite
            db_exp = db_token.expires_at.replace(tzinfo=timezone.utc)
        else:
            db_exp = db_token.expires_at

        if db_exp < now:
            db_token.revoked = True
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired. Please log in again.",
            )

        # Revoke old token (one-time rotation)
        db_token.revoked = True

        user = db.execute(select(User).where(User.id == db_token.user_id)).scalar_one_or_none()
        if not user or not user.is_active:
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account associated with this token is invalid or inactive.",
            )

        return AuthService.create_user_tokens(db, user)

    @staticmethod
    def revoke_refresh_token(db: Session, raw_refresh_token: str) -> None:
        """Revoke a refresh token (logout)."""
        token_hash = hash_token(raw_refresh_token)
        db_token = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()

        if db_token:
            db_token.revoked = True
            db.commit()

