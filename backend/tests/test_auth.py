"""Unit tests for user registration, login, and profile access."""

from __future__ import annotations


def test_register_success(client):
    """Test successful user registration returns access and refresh tokens."""
    payload = {
        "email": "ashish@example.com",
        "password": "SecurePassword123!",
        "full_name": "Ashish Sahoo",
    }
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_register_duplicate_email(client):
    """Test registration fails with 400 when email is already registered."""
    payload = {
        "email": "duplicate@example.com",
        "password": "SecurePassword123!",
        "full_name": "User One",
    }
    resp1 = client.post("/api/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/api/auth/register", json=payload)
    assert resp2.status_code == 400
    assert "already registered" in resp2.json()["detail"]


def test_login_success_and_profile(client):
    """Test valid login returns tokens, and access token allows profile retrieval."""
    reg_payload = {
        "email": "profile_test@example.com",
        "password": "Password789!",
        "full_name": "Profile Tester",
    }
    client.post("/api/auth/register", json=reg_payload)

    # Login
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "profile_test@example.com", "password": "Password789!"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    token = token_data["access_token"]

    # Access profile
    profile_resp = client.get(
        "/api/user/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["email"] == "profile_test@example.com"
    assert profile["full_name"] == "Profile Tester"
    assert profile["is_active"] is True


def test_login_wrong_password(client):
    """Test login failure with incorrect credentials returns 401."""
    reg_payload = {
        "email": "wrong_pass@example.com",
        "password": "CorrectPassword123!",
    }
    client.post("/api/auth/register", json=reg_payload)

    login_resp = client.post(
        "/api/auth/login",
        json={"email": "wrong_pass@example.com", "password": "WrongPassword!"},
    )
    assert login_resp.status_code == 401


def test_unauthorized_access(client):
    """Test protected routes reject missing or invalid token with 401."""
    resp_no_token = client.get("/api/user/profile")
    assert resp_no_token.status_code == 401

    resp_bad_token = client.get(
        "/api/user/profile",
        headers={"Authorization": "Bearer completely_bogus_token"},
    )
    assert resp_bad_token.status_code == 401


def test_update_preferences(client):
    """Test user can update their preferences successfully."""
    reg_payload = {
        "email": "prefs_user@example.com",
        "password": "Password123!",
    }
    reg_resp = client.post("/api/auth/register", json=reg_payload)
    token = reg_resp.json()["access_token"]

    update_resp = client.patch(
        "/api/user/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"preferences": {"theme": "light", "voice_speed": 1.2}},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["preferences"]["theme"] == "light"
    assert data["preferences"]["voice_speed"] == 1.2


def test_rate_limiting_enforced(client):
    """Test that rate limiter triggers 429 when enabled and limit is exceeded."""
    from backend.app.core.limiter import limiter
    limiter.enabled = True
    last_status = 200
    try:
        for i in range(15):
            resp = client.post(
                "/api/auth/register",
                json={"email": f"ratetest_{i}@example.com", "password": "Password123!"},
            )
            last_status = resp.status_code
            if last_status == 429:
                break
        assert last_status == 429
    finally:
        limiter.enabled = False
