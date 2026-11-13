import asyncio
import time
from unittest.mock import MagicMock
from backend.app.schemas.chat import ChatRequest
from backend.app.services.chat_service import ChatService
from backend.app.models.user import User
import backend.app.services.chat_service as cs
from backend.app.services.ai_provider import AIProvider


class CountingProvider(AIProvider):
    def __init__(self):
        self.calls = 0

    async def generate_response(self, prompt, system_prompt=""):
        self.calls += 1
        return ("Idempotent answer to: " + prompt, 42.0)

    async def check_health(self):
        return True, "mock-llama3.2", ""


async def run_idempotency_test():
    provider = CountingProvider()
    orig = cs.ai_provider
    cs.ai_provider = provider
    try:
        ChatService.clear_idempotency_cache()
        db = MagicMock()
        user = User(id="acc-user-01", email="acc@test.com", full_name="Acceptance User")
        req = ChatRequest(message="What is 2+2?", request_id=f"acc-{time.time()}")

        r1 = await ChatService.process_chat(db, user, req)
        r2 = await ChatService.process_chat(db, user, req)
        r3 = await ChatService.process_chat(db, user, req)

        print("All 3 replies identical:", r1.reply == r2.reply == r3.reply)
        print("Reply content:", r1.reply[:60])
        print("AI provider calls (expect 1):", provider.calls)
        print("T-C3 Backend Idempotency:", "PASS" if provider.calls == 1 else "FAIL")
    finally:
        cs.ai_provider = orig


asyncio.run(run_idempotency_test())

