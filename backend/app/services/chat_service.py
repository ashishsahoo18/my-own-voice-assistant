"""Chat service managing user-isolated conversations, messages, and AI generation."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.conversation import Conversation, Message
from backend.app.models.user import User
from backend.app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
)
from backend.app.services.ai_provider import ai_provider

_idempotency_cache: Dict[str, Tuple[float, ChatResponse]] = {}
_inflight_events: Dict[str, asyncio.Event] = {}


class ChatService:
    """Chat service with mandatory user-id filtering for absolute isolation."""

    @classmethod
    def clear_idempotency_cache(cls) -> None:
        """Clear in-memory idempotency caches (primarily for testing)."""
        _idempotency_cache.clear()
        _inflight_events.clear()

    @staticmethod
    async def process_chat(db: Session, user: User, req: ChatRequest) -> ChatResponse:
        """Process chat message, store interaction in database, and return AI response."""
        cache_key: Optional[str] = None
        is_initiator = False

        if req.request_id:
            cache_key = f"{user.id}:{req.request_id}"
            now = time.time()
            if cache_key in _idempotency_cache:
                ts, cached_resp = _idempotency_cache[cache_key]
                if now - ts < 600:  # 10 minutes TTL
                    return cached_resp

            if cache_key in _inflight_events:
                # Concurrent duplicate request in-flight: wait up to 30s for original to complete
                try:
                    await asyncio.wait_for(_inflight_events[cache_key].wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
                if cache_key in _idempotency_cache:
                    return _idempotency_cache[cache_key][1]

            _inflight_events[cache_key] = asyncio.Event()
            is_initiator = True

        try:
            conversation: Optional[Conversation] = None

            if req.conversation_id:
                # Strictly verify conversation belongs to authenticated user
                conversation = db.execute(
                    select(Conversation).where(
                        Conversation.id == req.conversation_id,
                        Conversation.user_id == user.id,
                    )
                ).scalar_one_or_none()

                if not conversation:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Conversation not found or access denied.",
                    )
            else:
                # Auto-create new conversation for user
                import uuid
                title = req.message.strip()[:40] if req.message.strip() else "New Chat"
                conversation = Conversation(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    title=title,
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)

            # 1. Save user message
            user_msg = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role="user",
                content=req.message.strip(),
            )
            db.add(user_msg)
            db.commit()

            # 2. Call AI Provider
            reply_text, latency_ms = await ai_provider.generate_response(req.message.strip())

            # 3. Save assistant message
            assistant_msg = Message(
                conversation_id=conversation.id,
                user_id=user.id,
                role="assistant",
                content=reply_text,
                latency_ms=latency_ms,
            )
            db.add(assistant_msg)
            db.commit()

            resp = ChatResponse(
                conversation_id=conversation.id,
                reply=reply_text,
                latency_ms=latency_ms,
                model="ollama/llama3.2",
            )

            if cache_key:
                _idempotency_cache[cache_key] = (time.time(), resp)

            return resp
        finally:
            if is_initiator and cache_key and cache_key in _inflight_events:
                event = _inflight_events.pop(cache_key, None)
                if event:
                    event.set()

    @staticmethod
    def get_user_conversations(db: Session, user: User) -> List[ConversationResponse]:
        """Fetch all conversations belonging to the authenticated user."""
        conversations = db.execute(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        ).scalars().all()

        return [
            ConversationResponse(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in conversations
        ]

    @staticmethod
    def get_conversation_messages(db: Session, user: User, conversation_id: str) -> ConversationDetailResponse:
        """Fetch all messages for a specific conversation, strictly verifying user ownership."""
        conversation = db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        ).scalar_one_or_none()

        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )

        messages = db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.user_id == user.id,
            )
            .order_by(Message.created_at.asc())
        ).scalars().all()

        return ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[
                MessageResponse(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    latency_ms=m.latency_ms,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )

