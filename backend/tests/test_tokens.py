"""Unit tests for token rotation, expiry, reuse detection, and revocation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.core.security import hash_token
from backend.app.models.token import RefreshToken


def test_token_refresh_and_rotation(client):
    """Test refreshing token returns a new pair and revokes the old refresh token."""
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "rotate_user@example.com", "password": "Password123!"},
    )
    assert reg_resp.status_code == 201
    old_refresh = reg_resp.json()["refresh_token"]

    # 1. Refresh using old refresh token
    refresh_resp = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    new_access = data["access_token"]
    new_refresh = data["refresh_token"]

    assert new_refresh != old_refresh

    # 2. Verify new access token works
    prof_resp = client.get(
        "/api/user/profile",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert prof_resp.status_code == 200

    # 3. Attempt to reuse old refresh token -> should be rejected and trigger reuse protection
    reuse_resp = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_resp.status_code == 401
    assert "reuse detected" in reuse_resp.json()["detail"].lower()


def test_expired_refresh_token(client, db_session):
    """Test that an expired refresh token is rejected with 401."""
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "expire_user@example.com", "password": "Password123!"},
    )
    raw_refresh = reg_resp.json()["refresh_token"]

    # Manually expire the token in the database
    token_h = hash_token(raw_refresh)
    token_record = db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_h)
    ).scalar_one()

    token_record.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()

    # Attempt to refresh
    resp = client.post("/api/auth/refresh", json={"refresh_token": raw_refresh})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_logout_revokes_token(client):
    """Test logout explicitly revokes refresh token."""
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "logout_user@example.com", "password": "Password123!"},
    )
    refresh_t = reg_resp.json()["refresh_token"]

    # Logout
    logout_resp = client.post("/api/auth/logout", json={"refresh_token": refresh_t})
    assert logout_resp.status_code == 200

    # Attempt to refresh with logged-out token
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_t})
    assert resp.status_code == 401

