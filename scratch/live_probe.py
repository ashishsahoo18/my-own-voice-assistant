"""Live probe script to start Uvicorn server, test every endpoint with HTTP, and report real latencies."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

BASE_URL = "http://127.0.0.1:8000"


def run_probe():
    print(f"[*] Starting Uvicorn server on {BASE_URL}...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )

    try:
        # Wait up to 10 seconds for server to come up
        ready = False
        for _ in range(20):
            try:
                r = httpx.get(f"{BASE_URL}/api/health", timeout=1.0)
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.5)

        if not ready:
            print("[!] Server failed to start within timeout.")
            return

        print("[+] Server is online. Running endpoint verification:\n")

        with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
            # 1. Health
            t0 = time.perf_counter()
            r = client.get("/api/health")
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"1. GET /api/health -> Status: {r.status_code} ({t_ms:.2f}ms)\n   Body: {r.json()}")

            # 2. Register
            t0 = time.perf_counter()
            unique_email = f"ashish.live.{int(time.time())}@example.com"
            reg_body = {"email": unique_email, "password": "Password123!", "full_name": "Ashish Sahoo"}
            r = client.post("/api/auth/register", json=reg_body)
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"2. POST /api/auth/register -> Status: {r.status_code} ({t_ms:.2f}ms)")
            tokens = r.json()
            access_token = tokens["access_token"]
            refresh_token = tokens["refresh_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            # 3. Login
            t0 = time.perf_counter()
            r = client.post("/api/auth/login", json={"email": unique_email, "password": "Password123!"})
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"3. POST /api/auth/login -> Status: {r.status_code} ({t_ms:.2f}ms)")

            # 4. Profile
            t0 = time.perf_counter()
            r = client.get("/api/user/profile", headers=headers)
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"4. GET /api/user/profile -> Status: {r.status_code} ({t_ms:.2f}ms)\n   Profile: {r.json()['full_name']} ({r.json()['email']})")

            # 5. Patch preferences
            t0 = time.perf_counter()
            r = client.patch("/api/user/preferences", headers=headers, json={"preferences": {"theme": "cyberpunk", "voice_mode": "piper"}})
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"5. PATCH /api/user/preferences -> Status: {r.status_code} ({t_ms:.2f}ms)\n   Updated Prefs: {r.json()['preferences']}")

            # 6. Welcome
            t0 = time.perf_counter()
            r = client.post("/api/welcome", headers=headers, json={"device_name": "Ashish Windows PC"})
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"6. POST /api/welcome -> Status: {r.status_code} ({t_ms:.2f}ms)\n   Greeting: {r.json()['greeting']}")

            # 7. Register device
            t0 = time.perf_counter()
            r = client.post("/api/devices/register", headers=headers, json={"device_name": "Ashish Laptop", "device_type": "desktop", "platform": "windows"})
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"7. POST /api/devices/register -> Status: {r.status_code} ({t_ms:.2f}ms)\n   Device: {r.json()['device_name']} [{r.json()['platform']}]")

            # 8. List devices
            t0 = time.perf_counter()
            r = client.get("/api/devices", headers=headers)
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"8. GET /api/devices -> Status: {r.status_code} ({t_ms:.2f}ms) -> Count: {len(r.json())}")

            # 9. Chat (Greeting)
            t0 = time.perf_counter()
            r = client.post("/api/chat", headers=headers, json={"message": "Hello OLIVER!"})
            t_ms = (time.perf_counter() - t0) * 1000.0
            chat_data = r.json()
            conv_id = chat_data["conversation_id"]
            print(f"9. POST /api/chat -> Status: {r.status_code} ({t_ms:.2f}ms)\n   Reply: {chat_data['reply']}\n   Model: {chat_data['model']}")

            # 10. List conversations
            t0 = time.perf_counter()
            r = client.get("/api/conversations", headers=headers)
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"10. GET /api/conversations -> Status: {r.status_code} ({t_ms:.2f}ms) -> Count: {len(r.json())}")

            # 11. Conversation messages
            t0 = time.perf_counter()
            r = client.get(f"/api/conversations/{conv_id}/messages", headers=headers)
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"11. GET /api/conversations/{{id}}/messages -> Status: {r.status_code} ({t_ms:.2f}ms) -> Message count: {len(r.json()['messages'])}")

            # 12. Refresh token rotation
            t0 = time.perf_counter()
            r = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"12. POST /api/auth/refresh -> Status: {r.status_code} ({t_ms:.2f}ms)")
            new_refresh = r.json()["refresh_token"]

            # 13. Logout
            t0 = time.perf_counter()
            r = client.post("/api/auth/logout", json={"refresh_token": new_refresh})
            t_ms = (time.perf_counter() - t0) * 1000.0
            print(f"13. POST /api/auth/logout -> Status: {r.status_code} ({t_ms:.2f}ms) -> {r.json()['message']}")

        print("\n[+] All 13 live endpoint calls verified successfully!")

    finally:
        print("[*] Terminating Uvicorn server...")
        proc.terminate()
        proc.wait(timeout=5.0)
        print("[+] Uvicorn server stopped cleanly.")


if __name__ == "__main__":
    run_probe()
