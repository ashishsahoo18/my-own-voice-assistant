"""Integration tests for health, welcome, and chat endpoints."""

from __future__ import annotations


def test_health_endpoint(client):
    """Test health check returns system status and dependencies."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "3.0.0"
    assert data["database"] == "connected"
    assert "ollama_status" in data


def test_welcome_endpoint(client):
    """Test welcome greeting endpoint requires authentication."""
    # Unauthenticated
    resp_unauth = client.post("/api/welcome", json={"device_name": "Test Laptop"})
    assert resp_unauth.status_code == 401

    # Authenticated
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "welcome_user@example.com", "password": "Password123!", "full_name": "Ashish Sahoo"},
    )
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/welcome", headers=headers, json={"device_name": "Office PC"})
    assert resp.status_code == 200
    data = resp.json()
    assert "Ashish" in data["greeting"]
    assert data["device_name"] == "Office PC"
    assert len(data["quick_tips"]) > 0


def test_chat_and_conversation_continuation(client):
    """Test sending multiple messages within an auto-created and continued conversation."""
    reg_resp = client.post(
        "/api/auth/register",
        json={"email": "chat_user@example.com", "password": "Password123!", "full_name": "Chatter"},
    )
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # First message (auto-creates conversation)
    chat1 = client.post("/api/chat", headers=headers, json={"message": "What is Python?"})
    assert chat1.status_code == 200
    data1 = chat1.json()
    conv_id = data1["conversation_id"]
    assert len(conv_id) == 36
    assert "reply" in data1
    assert data1["latency_ms"] >= 0.0

    # Second message continuing same conversation
    chat2 = client.post(
        "/api/chat",
        headers=headers,
        json={"conversation_id": conv_id, "message": "Give me an example"},
    )
    assert chat2.status_code == 200
    data2 = chat2.json()
    assert data2["conversation_id"] == conv_id

    # Retrieve conversation messages
    detail_resp = client.get(f"/api/conversations/{conv_id}/messages", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == conv_id
    # 2 user messages + 2 assistant responses = 4 messages
    assert len(detail["messages"]) == 4
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]

