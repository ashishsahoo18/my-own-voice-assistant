"""Multi-tenant isolation tests proving complete segregation between User A and User B."""

from __future__ import annotations


def test_cross_user_isolation_conversations_and_devices(client):
    """Rigorous verification: User B cannot access, read, or list User A's conversations or devices."""

    # 1. Register User A
    resp_a = client.post(
        "/api/auth/register",
        json={"email": "usera@example.com", "password": "Password123!", "full_name": "User Alpha"},
    )
    assert resp_a.status_code == 201
    token_a = resp_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # User A creates a conversation
    chat_a = client.post(
        "/api/chat",
        headers=headers_a,
        json={"message": "Confidential plan from User A"},
    )
    assert chat_a.status_code == 200
    conv_a_id = chat_a.json()["conversation_id"]

    # User A registers a device
    dev_a = client.post(
        "/api/devices/register",
        headers=headers_a,
        json={"device_name": "User A Laptop", "device_type": "desktop", "platform": "windows"},
    )
    assert dev_a.status_code == 200

    # 2. Register User B
    resp_b = client.post(
        "/api/auth/register",
        json={"email": "userb@example.com", "password": "Password456!", "full_name": "User Beta"},
    )
    assert resp_b.status_code == 201
    token_b = resp_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 3. Isolation Test: User B lists conversations -> MUST NOT include User A's conversation
    convs_b = client.get("/api/conversations", headers=headers_b)
    assert convs_b.status_code == 200
    conv_list_b = convs_b.json()
    assert len(conv_list_b) == 0  # User B has zero conversations

    # 4. Isolation Test: User B attempts to access User A's conversation messages directly by ID -> MUST return 404
    direct_access = client.get(f"/api/conversations/{conv_a_id}/messages", headers=headers_b)
    assert direct_access.status_code == 404
    assert "access denied" in direct_access.json()["detail"].lower() or "not found" in direct_access.json()["detail"].lower()

    # 5. Isolation Test: User B lists devices -> MUST NOT include User A's devices
    devices_b = client.get("/api/devices", headers=headers_b)
    assert devices_b.status_code == 200
    assert len(devices_b.json()) == 0

    # 6. User B registers device -> both lists remain strictly separated
    client.post(
        "/api/devices/register",
        headers=headers_b,
        json={"device_name": "User B Phone", "device_type": "mobile", "platform": "android"},
    )

    devs_a_check = client.get("/api/devices", headers=headers_a).json()
    devs_b_check = client.get("/api/devices", headers=headers_b).json()

    assert len(devs_a_check) == 1
    assert devs_a_check[0]["device_name"] == "User A Laptop"

    assert len(devs_b_check) == 1
    assert devs_b_check[0]["device_name"] == "User B Phone"

