"""Chat and conversation history routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.core.limiter import limiter
from backend.app.models.user import User
from backend.app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetailResponse,
    ConversationResponse,
)
from backend.app.services.chat_service import ChatService

router = APIRouter(prefix="/api", tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a chat message and receive an AI response."""
    return await ChatService.process_chat(db=db, user=current_user, req=body)


@router.get("/conversations", response_model=List[ConversationResponse])
def get_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all conversations belonging to the authenticated user."""
    return ChatService.get_user_conversations(db=db, user=current_user)


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationDetailResponse)
def get_conversation_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve all messages for a specific conversation owned by the authenticated user."""
    return ChatService.get_conversation_messages(
        db=db, user=current_user, conversation_id=conversation_id
    )

